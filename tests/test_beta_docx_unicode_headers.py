"""Regression: DOCX HTTP headers must not crash on Serbian/Cyrillic titles.

Live beta observation (2026-11-08): POST /api/staging/{id}/docx -> 500,
UnicodeEncodeError: latin-1 cannot encode U+017E in 'Odgovor na tužbu'.
No live OpenAI/Supabase calls are made by these tests.
"""

import pytest

from routers.drafting import _docx_content_disposition


@pytest.mark.parametrize("title,utf8_escaped", [
    ("Odgovor na tužbu", "Odgovor%20na%20tu%C5%BEbu.docx"),
    ("Žalba na rešenje", "%C5%BDalba%20na%20re%C5%A1enje.docx"),
    ("Одговор на тужбу", "%D0%9E%D0%B4%D0%B3%D0%BE%D0%B2%D0%BE%D1%80"),
])
def test_unicode_document_names_have_latin1_safe_headers_and_rfc5987(title, utf8_escaped):
    value = _docx_content_disposition(title)
    assert value.encode("latin-1")
    assert value.startswith('attachment; filename="')
    assert "; filename*=UTF-8''" in value
    assert utf8_escaped in value


def test_ascii_document_names_preserve_existing_content_disposition_contract():
    assert _docx_content_disposition("Odgovor na tuzbu") == (
        'attachment; filename="Odgovor na tuzbu.docx"'
    )


def test_header_injection_control_chars_are_sanitized():
    value = _docx_content_disposition('bad"\r\nX-Test: injected')
    assert '\r' not in value and '\n' not in value
    assert 'X-Test: injected' not in value
    assert value.encode("latin-1")


def test_empty_or_nonlatin_fallback_is_safe():
    for name in ("", "___", "Одговор на тужбу"):
        assert _docx_content_disposition(name).encode("latin-1")
