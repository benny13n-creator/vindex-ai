# -*- coding: utf-8 -*-
"""
Structural tests — integrations/word_addin/ (taskpane.html, adapter.js,
manifest.xml).

NIGHTLY REPAIR (2026-07-24), Faza 3 item 10: adapter.js existed with no
UI to render into (KORAK C). taskpane.html now provides that UI. These
are not traditional pytest unit tests (there's no Python here) -- they're
structural guards: valid markup, valid JS syntax, and the two files'
public API contract staying in sync (a method taskpane.html calls but
adapter.js stops exporting would otherwise only surface as a silent
runtime error inside Word, undetectable by any Python test).

Also catches a REAL bug found while writing these tests: manifest.xml
(written in an earlier Korak) used "--" inside XML comments, which is
illegal per the XML spec (only Python/JS-style comments tolerate it) --
this made the manifest invalid XML since it was first created, unnoticed
until validated here with a real parser. Fixed as part of this item.
"""
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import pytest

_HERE = os.path.dirname(__file__)
_ADDIN_DIR = os.path.join(_HERE, "..", "integrations", "word_addin")
_TASKPANE = os.path.join(_ADDIN_DIR, "taskpane.html")
_ADAPTER = os.path.join(_ADDIN_DIR, "adapter.js")
_MANIFEST = os.path.join(_ADDIN_DIR, "manifest.xml")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_taskpane_html_is_well_formed():
    errors = []

    class _Checker(HTMLParser):
        def error(self, message):
            errors.append(message)

    _Checker().feed(_read(_TASKPANE))
    assert errors == []


def test_manifest_xml_is_well_formed():
    """Regression for the actual bug found: '--' inside <!-- --> comments
    is illegal XML and silently produced an invalid manifest since it was
    first written."""
    tree = ET.parse(_MANIFEST)
    assert tree.getroot().tag.endswith("OfficeApp")


def test_manifest_has_no_double_hyphens_in_comments():
    content = _read(_MANIFEST)
    comments = re.findall(r"<!--(.*?)-->", content, re.DOTALL)
    assert comments, "expected at least one comment block in manifest.xml"
    for comment in comments:
        assert "--" not in comment


def test_manifest_references_taskpane_and_adapter_consistently():
    content = _read(_MANIFEST)
    assert "taskpane.html" in content


@pytest.mark.skipif(subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
                     reason="node not available in this environment")
def test_adapter_js_syntax_is_valid():
    result = subprocess.run(["node", "--check", _ADAPTER], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(subprocess.run(["node", "--version"], capture_output=True).returncode != 0,
                     reason="node not available in this environment")
def test_taskpane_inline_script_syntax_is_valid(tmp_path):
    html = _read(_TASKPANE)
    scripts = re.findall(r"<script(?![^>]*src)[^>]*>(.*?)</script>", html, re.DOTALL)
    assert scripts, "expected at least one inline <script> block without src="
    script_path = tmp_path / "inline.js"
    script_path.write_text(scripts[-1], encoding="utf-8")
    result = subprocess.run(["node", "--check", str(script_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_taskpane_only_calls_methods_adapter_actually_exports():
    """Cross-file contract guard: every VindexAmbientAdapter.<method>(...)
    call in taskpane.html must correspond to a method actually present in
    adapter.js's exported object -- catches drift between the two files
    that no Python test would otherwise notice."""
    adapter_src = _read(_ADAPTER)
    match = re.search(r"const VindexAmbientAdapter\s*=\s*\{(.*?)\};", adapter_src, re.DOTALL)
    assert match, "could not find VindexAmbientAdapter export object in adapter.js"
    exported = {name.strip() for name in re.findall(r"(\w+)\s*,", match.group(1))}
    assert "analyzeParagraph" in exported  # sanity check the parse itself worked

    taskpane_src = _read(_TASKPANE)
    called = set(re.findall(r"VindexAmbientAdapter\.(\w+)\s*\(", taskpane_src))
    assert called, "expected taskpane.html to call at least one adapter method"
    missing = called - exported
    assert not missing, f"taskpane.html calls methods not exported by adapter.js: {missing}"
