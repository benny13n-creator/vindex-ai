# -*- coding: utf-8 -*-
"""Structural and deterministic contract tests for the Word taskpane auth flow."""
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import pytest

_NODE = shutil.which("node")
_HERE = os.path.dirname(__file__)
_ADDIN_DIR = os.path.abspath(os.path.join(_HERE, "..", "integrations", "word_addin"))
_TASKPANE = os.path.join(_ADDIN_DIR, "taskpane.html")
_ADAPTER = os.path.join(_ADDIN_DIR, "adapter.js")
_MANIFEST = os.path.join(_ADDIN_DIR, "manifest.xml")
_AUTH_FLOW = os.path.join(_ADDIN_DIR, "auth_flow.js")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.mark.parametrize("filename", ["taskpane.html", "auth.html", "commands.html"])
def test_word_html_is_well_formed(filename):
    errors = []

    class Checker(HTMLParser):
        def error(self, message):
            errors.append(message)

    Checker().feed(_read(os.path.join(_ADDIN_DIR, filename)))
    assert errors == []


def test_manifest_xml_is_well_formed():
    tree = ET.parse(_MANIFEST)
    assert tree.getroot().tag.endswith("OfficeApp")


def test_manifest_references_taskpane():
    assert "taskpane.html" in _read(_MANIFEST)


def test_word_pages_use_external_scripts_only():
    for filename in ("taskpane.html", "auth.html", "commands.html"):
        html = _read(os.path.join(_ADDIN_DIR, filename))
        inline_scripts = re.findall(r"<script(?![^>]*src)[^>]*>(.*?)</script>", html, re.DOTALL)
        assert not inline_scripts, filename


@pytest.mark.skipif(_NODE is None, reason="node not available in this environment")
def test_word_javascript_syntax():
    for filename in ("auth_flow.js", "auth_dialog.js", "taskpane.js", "adapter.js", "commands.js"):
        path = os.path.join(_ADDIN_DIR, filename)
        result = subprocess.run([_NODE, "--check", path], capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, filename + ": " + result.stderr


def test_no_persistent_word_bearer_storage_or_automatic_analysis():
    adapter = _read(_ADAPTER)
    taskpane = _read(_TASKPANE)
    taskpane_js = _read(os.path.join(_ADDIN_DIR, "taskpane.js"))
    assert "localStorage.removeItem" in adapter
    assert "Office.context.roamingSettings" in adapter
    assert "settings.remove(LEGACY_TOKEN_KEY)" in adapter
    assert "localStorage.setItem" not in adapter
    assert "roamingSettings.get" not in adapter
    assert "roamingSettings.set" not in adapter
    assert "clearLegacyAuthToken" in taskpane_js
    assert "input-token" not in taskpane
    assert "analyzeParagraph" not in taskpane_js
    assert "watchParagraphChanges" not in taskpane_js


@pytest.mark.skipif(_NODE is None, reason="node not available in this environment")
def test_auth_callback_nonce_origin_and_session_token_contract():
    script = r"""
const assert = require('node:assert/strict');
const flow = require(process.argv[1]);
const nonce = flow.createNonce({getRandomValues(bytes) { bytes.fill(15); return bytes; }});
assert.equal(nonce, '0f'.repeat(32));
const message = JSON.stringify({type:'vindex-auth-result', nonce, access_token:'a.b.c'});
assert.equal(flow.parseAuthResult(message, 'https://vindex.test', 'https://vindex.test', nonce), 'a.b.c');
assert.throws(() => flow.parseAuthResult(message, 'https://evil.test', 'https://vindex.test', nonce), /invalid_callback_origin/);
assert.throws(() => flow.parseAuthResult(message, 'https://vindex.test', 'https://vindex.test', 'wrong'), /invalid_auth_callback/);
assert.throws(() => flow.parseAuthResult(JSON.stringify({type:'vindex-auth-result', nonce, access_token:'bad'}), 'https://vindex.test', 'https://vindex.test', nonce), /invalid_auth_callback/);
assert.equal(flow.isOpaqueSessionToken('x'.repeat(43)), true);
assert.equal(flow.isOpaqueSessionToken('x'.repeat(42)), false);
const supported = {context:{requirements:{isSetSupported(name, version) { return name === 'DialogApi' && version === '1.2' || name === 'DialogOrigin' && version === '1.1'; }}}};
assert.equal(flow.isDialogSupported(supported), true);
assert.equal(flow.isDialogSupported({context:{requirements:{isSetSupported() { return false; }}}}), false);
"""
    result = subprocess.run([_NODE, "-e", script, _AUTH_FLOW], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(_NODE is None, reason="node not available in this environment")
def test_legacy_token_cleanup_is_memory_safe_and_fails_closed():
    script = r"""
const assert = require('node:assert/strict');
let removedLocal = null;
let removedRoaming = null;
global.localStorage = {
  removeItem(key) { removedLocal = key; },
  getItem() { throw new Error('must not read a token'); },
  setItem() { throw new Error('must not persist a token'); }
};
global.Office = {
  context:{roamingSettings:{
    remove(key) { removedRoaming = key; },
    saveAsync(callback) { callback({status:'succeeded'}); }
  }},
  AsyncResultStatus:{Succeeded:'succeeded'}
};
const adapter = require(process.argv[1]);
(async () => {
  await adapter.clearLegacyAuthToken();
  assert.equal(removedLocal, 'vindex_auth_token');
  assert.equal(removedRoaming, 'vindex_auth_token');
  global.Office.context.roamingSettings.saveAsync = callback => callback({status:'failed'});
  await assert.rejects(adapter.clearLegacyAuthToken(), /legacy_roaming_token_cleanup_failed/);
  assert.deepEqual(Object.keys(adapter).sort(), [
    'applyApprovedRewrite', 'clearLegacyAuthToken', 'readSelectedText',
    'readSelectionSnapshot', 'supportsSafeRewrite'
  ].sort());
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run([_NODE, "-e", script, _ADAPTER], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
@pytest.mark.skipif(_NODE is None, reason="node not available in this environment")
def test_word_adapter_returns_exact_selected_range_text():
    script = r"""
const assert = require('node:assert/strict');
const adapter = require(process.argv[1]);
const exact = 'first line\nsecond\tcell';
let loaded = null;
let synced = false;
const office = {
  context: {
    document: {
      getSelection() {
        return {
          text: exact,
          load(field) { loaded = field; }
        };
      }
    },
    async sync() { synced = true; }
  }
};
(async () => {
  assert.equal(await adapter.readSelectedText(office), exact);
  assert.equal(loaded, 'text');
  assert.equal(synced, true);
  await assert.rejects(adapter.readSelectedText({}), /word_selection_unavailable/);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run([_NODE, "-e", script, _ADAPTER], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr

@pytest.mark.skipif(_NODE is None, reason="node not available in this environment")
def test_taskpane_session_races_and_window_isolation():
    path = os.path.join(_HERE, "word_addin_taskpane_behavior.js")
    result = subprocess.run([_NODE, path], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(_NODE is None, reason="node not available in this environment")
def test_word_rewrite_stale_range_and_mutation_safety_contract():
    path = os.path.join(_HERE, "word_addin_rewrite_behavior.js")
    result = subprocess.run([_NODE, path], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
@pytest.mark.skipif(_NODE is None, reason="node not available in this environment")
def test_auth_dialog_failed_and_successful_provider_responses():
    path = os.path.join(_HERE, "word_addin_auth_dialog_behavior.js")
    result = subprocess.run([_NODE, path], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
def test_manifest_has_no_double_hyphens_in_comments():
    comments = re.findall(r"<!--(.*?)-->", _read(_MANIFEST), re.DOTALL)
    assert all("--" not in comment for comment in comments)


def test_manifest_taskpane_adapter_and_exports_stay_consistent():
    manifest = _read(_MANIFEST)
    taskpane = _read(_TASKPANE)
    taskpane_js = _read(os.path.join(_ADDIN_DIR, "taskpane.js"))
    adapter = _read(_ADAPTER)

    assert "taskpane.html" in manifest
    assert '<script src="adapter.js"></script>' in taskpane
    for method in ("clearLegacyAuthToken", "readSelectedText"):
        assert method + ":" + method in adapter
        assert "VindexAmbientAdapter." + method in taskpane_js
