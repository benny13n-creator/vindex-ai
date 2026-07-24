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


# ═══════════════════════════════════════════════════════════════════════════
# Faza 2 — email HTML template escaping (routers/email_notif.py + support.py)
# ═══════════════════════════════════════════════════════════════════════════

_XSS_PAYLOAD = "<script>alert('xss')</script>"


class TestEmailNotifTemplatesEscaped:
    """CONFIRMED finding from the read-only analysis: routers/rocista.py's
    napomena (user free text) reached these templates' 'dogadjaj' field
    completely unescaped -- a real, traceable HTML-injection path into an
    email client. Faza 1 already strips HTML at the source (RocisteReq/
    FollowUpReq); these tests verify the independent, defense-in-depth
    escaping at the render site itself."""

    def test_email_html_escapes_dogadjaj_and_datum(self):
        from routers.email_notif import _email_html
        out = _email_html(
            [{"dogadjaj": _XSS_PAYLOAD + "Rok", "datum_iso": _XSS_PAYLOAD}],
            dana_pre=7,
        )
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_weekly_digest_html_escapes_user_name(self):
        from routers.email_notif import _weekly_digest_html
        out = _weekly_digest_html(
            user_name=_XSS_PAYLOAD, rokovi=[], rocista=[],
            aktivnih=1, neplaceno_rsd=0, hitnih=0,
        )
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_weekly_digest_html_escapes_rok_row_fields(self):
        from routers.email_notif import _weekly_digest_html
        out = _weekly_digest_html(
            user_name="Test", rokovi=[], rocista=[{"sud": _XSS_PAYLOAD, "datum": "2026-08-01"}],
            aktivnih=1, neplaceno_rsd=0, hitnih=0,
        )
        assert "<script>" not in out

    @pytest.mark.parametrize("fn_name", [
        "_onboarding_welcome_html", "_onboarding_day1_html", "_onboarding_day3_html",
    ])
    def test_onboarding_templates_escape_ime(self, fn_name):
        import routers.email_notif as en
        fn = getattr(en, fn_name)
        # email lokalni deo direktno postaje 'ime' -- '<script>' u local-part
        # nije standardan email, ali funkcija ne sme da padne niti da ga
        # propusti neescaped ako se ikad desi (npr. malformisan unos).
        out = fn(f"{_XSS_PAYLOAD}@example.com")
        assert "<script>" not in out


class TestSupportEmailTemplateEscaped:
    """Paralelna instanca iste klase buga, otkrivena tokom Faze 1 (support.py
    takodje gradi HTML email f-stringom). Otkrivena i ista imenska kolizija:
    fajl je koristio lokalnu promenljivu 'html' za string, sto bi se
    sudarilo sa 'import html' modulom -- preimenovano u 'html_body' pre
    dodavanja escaping-a."""

    def test_send_support_email_escapes_all_fields(self, monkeypatch):
        import routers.support as sp

        captured = {}

        class _FakeSMTP:
            def __init__(self, *a, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def ehlo(self): pass
            def starttls(self): pass
            def login(self, *a): pass
            def sendmail(self, from_addr, to_addrs, raw_bytes):
                captured["raw"] = raw_bytes

        monkeypatch.setattr(sp, "_SMTP_HOST", "localhost")
        monkeypatch.setattr(sp, "FOUNDER_EMAILS", {"founder@example.com"})
        monkeypatch.setattr(sp.smtplib, "SMTP", _FakeSMTP)

        sp._send_support_email(
            user_email=_XSS_PAYLOAD + "user@test.com",
            kategorija="tehnicko",
            poruka=_XSS_PAYLOAD + "Poruka",
            kontekst=_XSS_PAYLOAD,
        )
        assert "raw" in captured, "SMTP sendmail was never called"

        # Parsiraj pravi MIME poruku i proveri SAMO HTML body deo -- Subject
        # header legitimno sadrži sirov '<script>' tekst RFC-2047-enkodiran
        # (base64), što nije XSS rizik (email klijenti ne renderuju Subject
        # kao HTML) i ne treba da bude deo ove provere.
        import email as _email_pkg
        msg = _email_pkg.message_from_bytes(captured["raw"])
        html_parts = [
            part.get_payload(decode=True).decode("utf-8", errors="replace")
            for part in msg.walk()
            if part.get_content_type() == "text/html"
        ]
        assert html_parts, "Nijedan text/html deo nije pronađen u poruci"
        html_body = "".join(html_parts)
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body

    def test_html_body_variable_rename_did_not_break_sending(self, monkeypatch):
        """Strukturna provera protiv regresije imenske kolizije: fajl ne sme
        više da ima lokalnu promenljivu bukvalno nazvanu 'html' u
        _send_support_email (sudarala bi se sa 'import html')."""
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent / "routers" / "support.py").read_text(encoding="utf-8")
        fn_start = src.find("def _send_support_email(")
        fn_end = src.find("\ndef ", fn_start + 10)
        body = src[fn_start:fn_end if fn_end != -1 else fn_start + 3000]
        assert "html = f\"\"\"" not in body
        assert "html_body" in body


# ═══════════════════════════════════════════════════════════════════════════
# Faza 3 — konsolidacija escape funkcija u static/vindex.js
# ═══════════════════════════════════════════════════════════════════════════

_VINDEX_JS = None


def _vindex_js_source() -> str:
    global _VINDEX_JS
    if _VINDEX_JS is None:
        from pathlib import Path
        _VINDEX_JS = (Path(__file__).resolve().parent.parent / "static" / "vindex.js").read_text(encoding="utf-8")
    return _VINDEX_JS


_DUPLICATE_ESCAPE_FN_NAMES = ["_htmlEsc", "_ptEsc", "_pgEsc", "_fa_esc", "_htmlEscMd", "_miEsc", "_kalEsc"]


class TestEscHtmlConsolidationStructural:
    """Pre ovog sweep-a postojalo je 8 nezavisnih, dupliranih HTML-escape
    implementacija u vindex.js (escHtml + 7 varijanti) -- neke bez
    escaping-a navodnika (nebezbedne u attribute-kontekstu, npr. `data-
    tuzilac="..."` na liniji ~15028). Sada sve delegiraju jednoj kanonskoj
    `escHtml()`. Ovi testovi su strukturni (čitaju izvor) -- funkcionalni
    dokaz je u TestEscHtmlConsolidationRuntime ispod (stvarno izvršava JS
    preko node-a)."""

    def test_canonical_eschtml_escapes_all_five_chars(self):
        src = _vindex_js_source()
        idx = src.index("function escHtml(s)")
        snippet = src[idx:idx + 400]
        for ch_pattern in ["&amp;", "&lt;", "&gt;", "&quot;", "&#39;"]:
            assert ch_pattern in snippet, f"escHtml ne escape-uje {ch_pattern!r}"

    def test_canonical_eschtml_uses_null_check_not_falsy_check(self):
        """`if (!s) return ''` bi pretvorio 0/false u prazan string --
        kanonska verzija mora koristiti `s == null` (samo null/undefined)."""
        src = _vindex_js_source()
        idx = src.index("function escHtml(s)")
        snippet = src[idx:idx + 200]
        assert "s == null" in snippet or "s==null" in snippet

    @pytest.mark.parametrize("fn_name", _DUPLICATE_ESCAPE_FN_NAMES)
    def test_duplicate_functions_delegate_to_eschtml(self, fn_name):
        src = _vindex_js_source()
        idx = src.index(f"function {fn_name}(")
        # Telo funkcije (do prve '}') mora sadržati poziv escHtml(...), a NE
        # svoju sopstvenu .replace(/&/...) implementaciju.
        end = src.index("}", idx)
        body = src[idx:end + 1]
        assert "escHtml(" in body, f"{fn_name} više ne delegira escHtml()-u"
        assert ".replace(/&/g" not in body, f"{fn_name} i dalje ima sopstvenu escape implementaciju"

    def test_local_esc_inside_predmet_summary_delegates(self):
        """Lokalni `_esc` (unutar jedne funkcije, ne globalni) -- ista
        provera, drugačiji pattern jer je linija sažeta u jednu."""
        src = _vindex_js_source()
        idx = src.index("function _esc(s) {")
        line_end = src.index("\n", idx)
        line = src[idx:line_end]
        assert "escHtml(s)" in line
        assert ".replace(/&/g" not in line


class TestEscHtmlConsolidationRuntime:
    """Izvršava STVARNI JS (preko node-a, dostupnog u ovom environment-u)
    da dokaže da sve konsolidovane funkcije zaista produkuju identičan,
    ispravno eskejpovan izlaz -- ne samo da izvorni kod 'izgleda' ispravno."""

    @pytest.fixture(scope="class")
    def node_available(self):
        import shutil
        if shutil.which("node") is None:
            pytest.skip("node nije dostupan u ovom environment-u")
        return True

    def _run_node(self, script: str) -> str:
        import subprocess
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, f"node greška: {result.stderr}"
        return result.stdout

    def test_all_escape_functions_produce_identical_output(self, node_available):
        from pathlib import Path
        vindex_path = Path(__file__).resolve().parent.parent / "static" / "vindex.js"

        script = f"""
const fs = require('fs');
const lines = fs.readFileSync({vindex_path.as_posix()!r}, 'utf8').split('\\n');
function grabFn(name) {{
  const idx = lines.findIndex(l => l.startsWith('function ' + name + '('));
  if (idx === -1) throw new Error('not found: ' + name);
  let depth = 0, started = false, out = [];
  for (let i = idx; i < lines.length; i++) {{
    out.push(lines[i]);
    for (const ch of lines[i]) {{
      if (ch === '{{') {{ depth++; started = true; }}
      if (ch === '}}') depth--;
    }}
    if (started && depth === 0) break;
  }}
  return out.join('\\n');
}}
let src = grabFn('escHtml');
for (const n of {_DUPLICATE_ESCAPE_FN_NAMES!r}) {{ src += '\\n' + grabFn(n); }}
eval(src);
const payload = '<script>alert(1)</script>He said "hi" and it\\'s quoted';
const names = ['escHtml'].concat({_DUPLICATE_ESCAPE_FN_NAMES!r});
const results = names.map(n => eval(n)(payload));
console.log(JSON.stringify(results));
console.log(JSON.stringify([escHtml(null), escHtml(0), escHtml(false), escHtml(undefined)]));
"""
        out = self._run_node(script).strip().splitlines()
        import json
        results = json.loads(out[0])
        assert len(set(results)) == 1, f"Funkcije ne produkuju identičan izlaz: {list(zip(['escHtml'] + _DUPLICATE_ESCAPE_FN_NAMES, results))}"
        assert "&lt;script&gt;" in results[0]
        assert "&quot;hi&quot;" in results[0]
        assert "&#39;s" in results[0]

        edge_cases = json.loads(out[1])
        assert edge_cases == ["", "0", "false", ""], f"Edge-case ponašanje neočekivano: {edge_cases}"

    def test_markdown_rendering_still_escapes_before_inserting_tags(self, node_available):
        """_inlineMd (koristi _htmlEscMd -> escHtml) mora i dalje da
        escape-uje sirov HTML PRE nego što ubaci sopstvene <strong>/<em>/
        <code> tagove -- konsolidacija ne sme pokvariti markdown rendering."""
        from pathlib import Path
        vindex_path = Path(__file__).resolve().parent.parent / "static" / "vindex.js"
        script = f"""
const fs = require('fs');
const lines = fs.readFileSync({vindex_path.as_posix()!r}, 'utf8').split('\\n');
function grabFn(name) {{
  const idx = lines.findIndex(l => l.startsWith('function ' + name + '('));
  if (idx === -1) throw new Error('not found: ' + name);
  let depth = 0, started = false, out = [];
  for (let i = idx; i < lines.length; i++) {{
    out.push(lines[i]);
    for (const ch of lines[i]) {{
      if (ch === '{{') {{ depth++; started = true; }}
      if (ch === '}}') depth--;
    }}
    if (started && depth === 0) break;
  }}
  return out.join('\\n');
}}
eval(grabFn('escHtml') + '\\n' + grabFn('_htmlEscMd') + '\\n' + grabFn('_inlineMd'));
console.log(_inlineMd('<script>x</script> **bold**'));
"""
        out = self._run_node(script).strip()
        assert "<script>" not in out
        assert "&lt;script&gt;" in out
        assert "<strong>bold</strong>" in out


# ═══════════════════════════════════════════════════════════════════════════
# Faza 4 — ciljana provera preostalih innerHTML mesta
# ═══════════════════════════════════════════════════════════════════════════

class TestFaza4RemainingInnerHtmlSites:
    """Ciljana provera (ne uzorak) svih innerHTML mesta koja referenciraju
    poznata korisnička/klijentska polja (opis, napomena, beleska, sadrzaj,
    komentar, adresa, firma, naziv, tuzilac, ...). Rezultat ove provere:
    519 ukupno innerHTML mesta, svega par desetina referenciraju ova polja,
    i SVA su bila već ispravno eskejpovana OSIM jednog konkretnog,
    značajnog nalaza -- videti test_pdf_export_firma_fields_escaped."""

    def test_pdf_export_firma_fields_escaped(self):
        """KONKRETAN NALAZ (2026-07-24): firma.naziv/adresa/pib/kontakt
        (čitani iz localStorage -- korisnik ih unosi u podešavanjima) su
        bili umetnuti u PDF-export bodyHtml BEZ IKAKVOG escaping-a, a
        bodyHtml se stvarno renderuje kao HTML (container.innerHTML +
        Blob-HTML fallback koji se otvara u browseru) -- potvrđen
        stored-XSS put preko localStorage vrednosti korisnika, drugačiji
        rendering-kontekst od bilo čega drugog u ovom sweep-u."""
        src = _vindex_js_source()
        idx = src.index("firma-naziv\">'+")
        snippet = src[idx:idx + 60]
        assert "escHtml(firma.naziv" in snippet

        idx2 = src.index("firma-info\">'+")
        snippet2 = src[idx2:idx2 + 200]
        assert "escHtml(firma.adresa)" in snippet2
        assert "escHtml(firma.pib)" in snippet2
        assert "escHtml(firma.kontakt" in snippet2

    def test_pdf_section_value_uses_canonical_escape(self):
        src = _vindex_js_source()
        idx = src.index('class="pdf-val">')
        snippet = src[idx:idx + 80]
        assert "escHtml(val)" in snippet
        assert ".replace(/&/g" not in snippet

    @pytest.mark.parametrize("fn_name,marker", [
        ("stratFormatirajRezultat", "escHtml(tekst)"),
        ("web3FormatirajRezultat", "escHtml(tekst)"),
        ("_compareMarkdownToHtml", "escHtml(md)"),
    ])
    def test_ai_output_formatters_delegate_to_canonical_escape(self, fn_name, marker):
        """Ove funkcije formatiraju AI-generisani tekst (strategy debate,
        web3 analiza, document-compare markdown) -- otkrivene tek u Fazi 4
        jer njihova imena ne sadrže 'esc', pa ih Faza 3's regex-based
        pretraga (za funkcije imenovane *esc*) nije našla."""
        src = _vindex_js_source()
        idx = src.index(f"function {fn_name}(")
        end = src.index("\n\n", idx)
        body = src[idx:end]
        assert marker in body
        assert ".replace(/&/g" not in body

    def test_praksa_render_functions_delegate_to_canonical_escape(self):
        src = _vindex_js_source()
        for fn_name in ["praksa_render_card", "praksa_render_grupisano"]:
            idx = src.index(f"function {fn_name}(")
            end = src.index("\n\n", idx)
            body = src[idx:end]
            assert "escHtml(" in body
            assert ".replace(/&/g" not in body

    def test_ugovor_stampaj_escapes_tekst(self):
        src = _vindex_js_source()
        idx = src.index("function ugovor_stampaj(")
        end = src.index("\n\n", idx)
        body = src[idx:end]
        assert "escHtml(tekst)" in body
        assert ".replace(/&/g" not in body

    def test_no_remaining_inline_escape_chains_outside_canonical(self):
        """Konačna provera: JEDINO mesto u celom fajlu koje sadrži sirovi
        `.replace(/&/g,...)` lanac je sama kanonska escHtml() definicija --
        sve drugo mora delegirati."""
        src = _vindex_js_source()
        occurrences = src.count(".replace(/&/g")
        assert occurrences == 1, (
            f"Očekivano tačno 1 pojavljivanje (kanonska escHtml), nađeno {occurrences} -- "
            "neko mesto možda ima sopstvenu, nekonsolidovanu escape implementaciju."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
