"""Deterministic checks for the separate controlled Word release candidate."""
import os
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ADDIN_DIR = os.path.join(_ROOT, "integrations", "word_addin")
_MANIFEST = os.path.join(_ADDIN_DIR, "manifest.release.xml")
_MAIN_NS = "http://schemas.microsoft.com/office/appforoffice/1.1"
_BT_NS = "http://schemas.microsoft.com/office/officeappbasictypes/1.0"


def test_release_candidate_manifest_is_distinct_and_non_development():
    root = ET.parse(_MANIFEST).getroot()
    assert root.tag == f"{{{_MAIN_NS}}}OfficeApp"
    addin_id = uuid.UUID(root.findtext(f"{{{_MAIN_NS}}}Id"))
    dev_id = ET.parse(os.path.join(_ADDIN_DIR, "manifest.xml")).getroot().findtext(
        f"{{{_MAIN_NS}}}Id"
    )
    assert str(addin_id) != dev_id
    assert str(addin_id) != "00000000-0000-0000-0000-000000000000"
    assert root.findtext(f"{{{_MAIN_NS}}}Version") == "0.2.0.0"
    assert root.find(f"{{{_MAIN_NS}}}AppDomains") is None

    serialized = ET.tostring(root, encoding="unicode").lower()
    for forbidden in ("localhost", "127.0.0.1", "placeholder", "development"):
        assert forbidden not in serialized


def test_release_candidate_urls_are_https_same_origin_and_resolve_locally():
    root = ET.parse(_MANIFEST).getroot()
    urls = []
    for element in root.iter():
        value = element.attrib.get("DefaultValue", "")
        if value.startswith("http"):
            urls.append(value)

    assert urls
    assert all(urlparse(value).scheme == "https" for value in urls)
    assert {urlparse(value).hostname for value in urls} == {"vindex.rs"}
    assert root.find(f"{{{_MAIN_NS}}}SupportUrl").attrib["DefaultValue"] == (
        "https://vindex.rs/app"
    )

    asset_urls = [url for url in urls if urlparse(url).path.startswith("/word_addin/")]
    assert asset_urls
    for value in asset_urls:
        path = urlparse(value).path
        relative = path.removeprefix("/word_addin/")
        assert os.path.isfile(os.path.join(_ADDIN_DIR, relative)), value

    api_source = open(os.path.join(_ROOT, "api.py"), encoding="utf-8").read()
    assert '"/word_addin"' in api_source


def test_release_candidate_manifest_resource_references_are_defined():
    root = ET.parse(_MANIFEST).getroot()
    declared = {
        element.attrib["id"]
        for element in root.iter()
        if element.tag.startswith(f"{{{_BT_NS}}}") and "id" in element.attrib
    }
    referenced = {
        element.attrib["resid"]
        for element in root.iter()
        if "resid" in element.attrib
    }
    assert referenced <= declared
    assert root.find(f"{{{_MAIN_NS}}}Hosts/{{{_MAIN_NS}}}Host").attrib["Name"] == "Document"
