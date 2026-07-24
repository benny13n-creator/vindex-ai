# -*- coding: utf-8 -*-
"""
XSS & Input Sanitization Sweep (2026-07-24) — regression tests.

Faza 1: security/html_sanitize.py::sanitize_user_input() + Pydantic
field_validators applied across the routers identified in the read-only
analysis (predmet opis/naziv/beleske, klijenti, komentari, rocista/
napomena — the confirmed email-injection source, drafting, support,
dokument).

Faza 2/3/4 tests are appended to this same file as those phases complete.
"""
import os

import pytest

os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars-ok")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("PINECONE_HOST", "https://fake.pinecone.io")
os.environ.setdefault("FOUNDER_EMAILS", "founder@example.com")

from security.html_sanitize import sanitize_user_input  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# Faza 1a — sanitize_user_input core behavior
# ═══════════════════════════════════════════════════════════════════════════

class TestSanitizeUserInputCore:
    def test_strips_script_tag(self):
        assert "<script>" not in sanitize_user_input("<script>alert(1)</script>Opis")
        assert "alert(1)" in sanitize_user_input("<script>alert(1)</script>Opis")  # tekst ostaje, tag ne

    def test_strips_img_onerror(self):
        result = sanitize_user_input('<img src=x onerror=alert(1)>Beleska')
        assert "<img" not in result
        assert "onerror" not in result

    def test_preserves_newlines(self):
        s = "Prvi red\nDrugi red\n\nTreci red"
        assert sanitize_user_input(s) == s

    def test_preserves_markdown_syntax(self):
        s = "Kupio sam *3* kuce - sve u Beogradu\n- prva\n- druga\n# Naslov\n**bold** i `kod`"
        assert sanitize_user_input(s) == s

    def test_none_passes_through(self):
        assert sanitize_user_input(None) is None

    def test_empty_string_passes_through(self):
        assert sanitize_user_input("") == ""

    def test_plain_text_unaffected(self):
        s = "Ovo je obican opis predmeta bez ikakvog markupa."
        assert sanitize_user_input(s) == s

    def test_no_default_truncation_for_long_legitimate_text(self):
        """Regresija uhvaćena pre prvog test-run-a: default max_len=20000 bi
        tiho odsjekao polja poput DokumentAnalizaReq.tekst (Field max_length=
        80000) i AnalizaReq.tekst (50000) -- max_len=None (sada podrazumevano)
        ne sme skraćivati čak ni vrlo dug, potpuno legitiman tekst."""
        long_text = "Ovo je pravni tekst. " * 4000  # ~84,000 karaktera
        result = sanitize_user_input(long_text)
        assert len(result) == len(long_text)
        assert result == long_text

    def test_explicit_max_len_still_works_when_requested(self):
        assert len(sanitize_user_input("a" * 100, max_len=10)) == 10


# ═══════════════════════════════════════════════════════════════════════════
# Faza 1b — Pydantic models across target routers
# ═══════════════════════════════════════════════════════════════════════════

_PAYLOAD = "<script>alert('xss')</script>Legitimni tekst"
_EXPECTED_STRIPPED = "alert('xss')Legitimni tekst"


class TestRocistaModelsSanitize:
    """rocista.py's napomena is the CONFIRMED source that reaches
    routers/email_notif.py's unescaped HTML template (Faza 2) -- highest
    priority target in this sweep."""

    def test_rociste_req_napomena(self):
        from routers.rocista import RocisteReq
        r = RocisteReq(predmet_id="p1", sud="Osnovni sud", datum="2026-08-01",
                        napomena=_PAYLOAD)
        assert r.napomena == _EXPECTED_STRIPPED

    def test_rociste_patch_req_napomena(self):
        from routers.rocista import RocistePatchReq
        r = RocistePatchReq(napomena=_PAYLOAD)
        assert r.napomena == _EXPECTED_STRIPPED

    def test_followup_req_napomena(self):
        from routers.rocista import FollowUpReq
        r = FollowUpReq(predmet_id="p1", napomena=_PAYLOAD)
        assert r.napomena == _EXPECTED_STRIPPED


class TestKlijentiModelsSanitize:
    def test_klijent_create_req_fields(self):
        from klijenti.router import KlijentCreateReq
        k = KlijentCreateReq(ime=_PAYLOAD, prezime=_PAYLOAD, firma=_PAYLOAD,
                              adresa=_PAYLOAD, napomena=_PAYLOAD)
        assert k.ime == _EXPECTED_STRIPPED
        assert k.prezime == _EXPECTED_STRIPPED
        assert k.firma == _EXPECTED_STRIPPED
        assert k.adresa == _EXPECTED_STRIPPED
        assert k.napomena == _EXPECTED_STRIPPED

    def test_komunikacija_req_kratak_opis(self):
        from klijenti.router import KomunikacijaReq
        r = KomunikacijaReq(tip="poziv", datum_vreme="2026-08-01T10:00:00",
                             kratak_opis=_PAYLOAD)
        assert r.kratak_opis == _EXPECTED_STRIPPED

    def test_conflict_check_req_fields(self):
        from klijenti.router import ConflictCheckReq
        r = ConflictCheckReq(ime=_PAYLOAD)
        assert r.ime == _EXPECTED_STRIPPED


class TestKomentariModelSanitize:
    def test_komentar_request(self):
        from routers.komentari import KomentarRequest
        r = KomentarRequest(tekst=_PAYLOAD)
        assert r.tekst == _EXPECTED_STRIPPED

    def test_komentar_update_request(self):
        from routers.komentari import KomentarUpdateRequest
        r = KomentarUpdateRequest(tekst=_PAYLOAD)
        assert r.tekst == _EXPECTED_STRIPPED


class TestEnterpriseModelSanitize:
    def test_delegiranje_request_napomena(self):
        from routers.enterprise import DelegiranjeRequest
        r = DelegiranjeRequest(predmet_id="p1", advokat_user_id="u1", napomena=_PAYLOAD)
        assert r.napomena == _EXPECTED_STRIPPED


class TestDraftingModelsSanitize:
    def test_nacrt_req(self):
        from routers.drafting import NacrtReq
        r = NacrtReq(vrsta=_PAYLOAD, opis="Dovoljno dugacak opis za validaciju" + _PAYLOAD)
        assert r.vrsta == _EXPECTED_STRIPPED

    def test_analiza_req_long_text_not_truncated(self):
        """Konkretna regresija koju je ovaj sweep uveo pa odmah uhvatio:
        AnalizaReq.tekst dozvoljava do 50,000 karaktera -- sanitizacija ne
        sme tiho odseći legitiman dugačak tekst. (.strip() na kraju je
        očekivano, postojeće ponašanje ovog validatora od pre ovog sweep-a
        -- upoređujemo protiv .strip()-ovane vrednosti, ne sirove.)"""
        from routers.drafting import AnalizaReq
        long_text = "Ugovorna odredba. " * 2000  # ~36,000 karaktera, i dalje pod 50k
        r = AnalizaReq(tekst=long_text, pitanje="Da li je ovo validno?")
        assert r.tekst == long_text.strip()
        assert len(r.tekst) > 35000

    def test_podnesak_req_opis(self):
        from routers.drafting import PodnesakReq
        r = PodnesakReq(tip="tuzba_naknada_stete",
                         opis="Dovoljno dugacak opis za validaciju polja" + _PAYLOAD)
        assert "<script>" not in r.opis

    def test_nacrt_checklist_req_cinjenice(self):
        from routers.drafting import NacrtChecklistReq
        from nacrti.checklist_config import SVI_TIPOVI
        tip = next(iter(SVI_TIPOVI))
        r = NacrtChecklistReq(tip=tip, cinjenice="Cinjenice dovoljno duge za validaciju" + _PAYLOAD)
        assert "<script>" not in r.cinjenice

    def test_feedback_req(self):
        from routers.drafting import FeedbackReq
        r = FeedbackReq(pitanje=_PAYLOAD, odgovor=_PAYLOAD)
        assert r.pitanje == _EXPECTED_STRIPPED
        assert r.odgovor == _EXPECTED_STRIPPED


class TestSupportModelSanitize:
    def test_support_poruka(self):
        from routers.support import SupportPoruka
        r = SupportPoruka(poruka="Dovoljno duga poruka za validaciju " + _PAYLOAD)
        assert "<script>" not in r.poruka

    def test_support_poruka_kontekst(self):
        from routers.support import SupportPoruka
        r = SupportPoruka(poruka="Dovoljno duga poruka za validaciju polja",
                           kontekst=_PAYLOAD)
        assert r.kontekst == _EXPECTED_STRIPPED


class TestDokumentModelsSanitize:
    def test_pitanje_doc_request(self):
        from routers.dokument import PitanjeDocRequest
        r = PitanjeDocRequest(session_id="s1", pitanje=_PAYLOAD)
        assert r.pitanje == _EXPECTED_STRIPPED

    def test_dokument_analiza_req_long_text_not_truncated(self):
        """DokumentAnalizaReq.tekst dozvoljava do 80,000 karaktera -- ista
        klasa regresije kao AnalizaReq iznad, viša granica. (.strip() na
        kraju je postojeće ponašanje _trim validatora, ne posledica ovog
        sweep-a.)"""
        from routers.dokument import DokumentAnalizaReq
        long_text = "Dokument sadrzaj. " * 3000  # ~54,000 karaktera
        r = DokumentAnalizaReq(tekst=long_text, pitanje="pitanje")
        assert r.tekst == long_text.strip()
        assert len(r.tekst) > 50000


class TestApiPyPredmetiHandlersUseSanitizer:
    """kreiraj_predmet/update_predmet/dodaj_belesku rade sa raw dict-om
    (nema Pydantic model), pa se ne mogu testirati kroz model konstrukciju
    -- strukturna provera da sanitize_user_input() poziv postoji uz svako
    upisno mesto."""

    @pytest.fixture(scope="class")
    def api_src(self):
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "api.py").read_text(encoding="utf-8")

    def test_kreiraj_predmet_sanitizes_naziv_and_opis(self, api_src):
        idx = api_src.find('async def kreiraj_predmet(')
        assert idx != -1
        snippet = api_src[idx:idx + 700]
        assert "sanitize_user_input" in snippet
        assert 'sanitize_user_input(body.get("opis"' in snippet

    def test_update_predmet_sanitizes_text_fields(self, api_src):
        idx = api_src.find('async def update_predmet(')
        assert idx != -1
        snippet = api_src[idx:idx + 900]
        assert "sanitize_user_input" in snippet

    def test_dodaj_belesku_sanitizes_sadrzaj(self, api_src):
        idx = api_src.find('async def dodaj_belesku(')
        assert idx != -1
        snippet = api_src[idx:idx + 1200]
        assert "sanitize_user_input" in snippet


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
