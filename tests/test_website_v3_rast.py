# -*- coding: utf-8 -*-
"""
Website V3 — pozicioniranje, uklonjen javni razvoj, primena po sektorima,
stranica o bezbednosti i prijava problema iz V2 aplikacije.

Founder mandat „Website V3 / Growth Experience Sprint“ (2026-10-21). Ugovori:

  1. Početna kaže šta je Vindex, zašto i šta je sledeći korak; jedini primarni
     poziv je „Prijavi se za rani pristup“ (/beta, postojeća waitlist ruta).
  2. Sektori opisuju VRSTU posla, ne gotov proizvod: samo advokatske kancelarije
     su označene kao ono za šta je Vindex danas napravljen.
  3. /bezbednost odgovara na stvarna pitanja i ne krije materijalne činjenice
     (servisni ključ, bez rezervnih kopija, SCC nije potvrđen, Pinecone segmenti);
     poređenje sa opštim AI asistentom ne tvrdi da je Vindex bezbedniji.
  4. POST /api/support/poruka ne javlja uspeh za poruku koja nije sačuvana ni
     poslata; identitet je iz tokena; HTML i zaglavlje emaila su zaštićeni.
  5. V2 kontrola za prijavu problema šalje samo kategoriju, opis i naziv ekrana.
"""
import itertools
import os
import re
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api  # noqa: E402
import routers.support as sp  # noqa: E402
from shared.deps import get_current_user  # noqa: E402

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTA = "Prijavi se za rani pristup"


@pytest.fixture(scope="module")
def k():
    return TestClient(api.app)


def _cist(k, ruta):
    t = k.get(ruta).text
    t = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def _odeljak(html, id_naslova):
    m = re.search(rf'<section[^>]*aria-labelledby="{id_naslova}"[^>]*>(.*?)</section>', html, flags=re.S)
    assert m, f"nema odeljka {id_naslova}"
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1)))


# ═══════════════════════════════════════════════════════════════════════════
# 1. Početna i poziv na akciju
# ═══════════════════════════════════════════════════════════════════════════

def test_prvi_ekran_kaze_sta_je_vindex_i_sledeci_korak(k):
    t = k.get("/").text
    hero = re.search(r'<section class="uvod uvod--glavni".*?</section>', t, flags=re.S).group(0)
    assert "Od dokumenata do jasnih odluka." in hero
    assert "Pravni radni prostor" in hero                       # kategorija
    assert "vezan za izvor" in hero and "potvrdi" in hero       # razlika: izvor i potvrda
    dugmad = re.findall(r'<a class="dugme[^"]*" href="([^"]+)">([^<]+)</a>', hero)
    assert dugmad == [("/beta", CTA)], dugmad                    # jedan primarni poziv
    assert 'href="/kako-radi">Pogledaj kako Vindex radi</a>' in hero
    assert 'class="snimak uvod__snimak' in hero                  # stvaran ekran


@pytest.mark.parametrize("ruta", ["/", "/kako-radi", "/funkcionalnosti", "/za-advokate", "/bezbednost", "/beta"])
def test_poziv_za_rani_pristup_je_dosledan(k, ruta):
    t = k.get(ruta).text
    for href, tekst in re.findall(r'<a class="dugme[^"]*" href="(/beta)">([^<]+)</a>', t):
        assert tekst == CTA, f"{ruta}: dugme ka /beta glasi {tekst!r}"
    zaglavlje = re.search(r'<header class="zaglavlje">.*?</header>', t, flags=re.S).group(0)
    assert zaglavlje.count(f'href="/beta">{CTA}</a>') == 2      # desktop i mobilni meni
    assert "Beta pristup" not in t and "Prijavite se za beta testiranje" not in t


def test_rani_pristup_koristi_postojecu_waitlist_rutu_i_ne_obecava_nalog(k):
    t = _cist(k, "/beta")
    assert "Prijavi se za rani pristup Vindexu." in t
    assert "sama prijava ne otvara nalog" in t
    assert "beta testiranje" in t                                 # svrha iz Politike privatnosti
    assert "/waitlist/prijava" in k.get("/v2/site/sajt.js").text


def test_istaknute_funkcije_su_dostupne_i_vode_na_katalog(k):
    t = k.get("/").text
    clanci = re.findall(r'<article class="istaknuto[^"]*".*?</article>', t, flags=re.S)
    assert 3 <= len(clanci) <= 5
    katalog = k.get("/funkcionalnosti").text
    for c in clanci:
        for dt in ("Problem", "Šta Vindex radi", "Vaša korist"):
            assert f"<dt>{dt}</dt>" in c
        sidro = re.search(r'href="/funkcionalnosti#([^"]+)"', c).group(1)
        assert f'id="{sidro}"' in katalog, sidro
        assert "Demonstracioni prikaz" in c


# ═══════════════════════════════════════════════════════════════════════════
# 2. Sektori — vrsta posla, ne gotov proizvod
# ═══════════════════════════════════════════════════════════════════════════

SEKTORI = ["Advokatske kancelarije", "Javnobeležničke kancelarije", "Pravni sektori kompanija",
           "Osiguravajuće kuće", "Banke i finansijske institucije", "Timovi za usklađenost i regulativu",
           "Računovodstvene i revizorske organizacije", "Konsultantske organizacije",
           "Korporativna administracija i ugovorni timovi", "Timovi sa mnogo dokumenata"]


def test_sektori_razlikuju_danasnju_namenu_od_moguce_primene(k):
    t = k.get("/").text
    kartice = re.findall(r'<li class="sektor([^"]*)"[^>]*><span class="sektor__status">([^<]+)</span>\s*<h3>([^<]+)</h3>', t)
    assert [n for _, _, n in kartice] == SEKTORI
    for klasa, status, naziv in kartice:
        if naziv == "Advokatske kancelarije":
            assert "sektor--danas" in klasa and status == "Za ovo je Vindex napravljen"
        else:
            assert "sektor--danas" not in klasa and status == "Moguća primena", naziv
    o = _odeljak(t, "sektori-naslov")
    assert "nema posebne module" in o and "ne gotov proizvod" in o


def test_sektori_ne_tvrde_sertifikaciju_odobrenje_ni_spremnost(k):
    o = _odeljak(k.get("/").text, "sektori-naslov").lower()
    for rx in (r"sertifikovan", r"certifi", r"odobren od", r"usklađen sa", r"spreman za", r"bank-grade",
               r"koriste nas", r"klijenti iz", r"implementiran"):
        assert not re.search(rx, o), rx


# ═══════════════════════════════════════════════════════════════════════════
# 3. Bezbednost
# ═══════════════════════════════════════════════════════════════════════════

PITANJA = {"pristup": "Ko može da pristupi mojim podacima?", "cuvanje": "Gde se čuvaju podaci?",
           "ai": "Šta se šalje AI modelu?", "dokumenti": "Kako su dokumenti zaštićeni?",
           "izvoz": "Kako se podaci izvoze?", "brisanje": "Šta se dešava pri brisanju?",
           "upravljanje": "Ko upravlja podacima?"}


def test_bezbednost_odgovara_na_pitanja_korisnika(k):
    t = k.get("/bezbednost").text
    for sidro, pitanje in PITANJA.items():
        assert f'id="{sidro}"' in t and pitanje in t, sidro
        assert f'href="#{sidro}"' in t


def test_bezbednost_ne_krije_materijalne_cinjenice(k):
    t = _cist(k, "/bezbednost")
    for cinjenica in ("servisnim ključem", "ne beleži evidencija aplikacije",          # pristup
                      "Supabase", "Render", "OpenAI", "Pinecone",                        # dobavljači
                      "SCC) sa dobavljačima u SAD nije potvrđeno",
                      "Automatske rezervne kopije baze trenutno nisu uključene",
                      "napušta Vindexovu infrastrukturu",                                # AI
                      "nije dodatno šifrovan",                                           # tekst
                      "Originalni fajlovi", "nisu u toj arhivi",                         # izvoz
                      "brisanjem naloga ne brišu",                                       # Pinecone
                      "rukovalac ste vi", "kao obrađivač",                               # uloge
                      "nema nezavisnu bezbednosnu sertifikaciju"):
        assert cinjenica in t, cinjenica


def test_poredjenje_sa_opstim_ai_asistentom_je_posteno(k):
    o = _odeljak(k.get("/bezbednost").text, "poredjenje-naslov")
    assert "ChatGPT" in o
    assert "ne tvrdi da je jedan alat bezbedniji od drugog" in o
    assert "pamte kontekst" in o and "priloženim fajlovima" in o     # šta opšti asistent ume
    assert "OpenAI" in o                                             # Vindex koristi spoljni model
    for rx in (r"bezbedniji od (chatgpt|opšt)", r"sigurniji od", r"chatgpt (ne|nema) ", r"za razliku od chatgpt",
               r"privatniji", r"nikad ne napuštaju"):
        assert not re.search(rx, o, re.I), rx


def test_opis_izvoza_i_brisanja_odgovara_kodu(k):
    """Stranica kaže: ZIP sa JSON-om bez originala; brisanje naloga je samouslužno. Kod mora to i da radi."""
    with open(os.path.join(KOREN, "routers", "data_export.py"), encoding="utf-8") as f:
        izvoz = f.read()
    assert "ZIP sa JSON fajlovima (bez originalnih fajlova dokumenata)" in izvoz
    with open(os.path.join(KOREN, "index.html"), encoding="utf-8-sig") as f:
        legacy = f.read()
    assert 'onclick="obrisiNalogSelfService()"' in legacy
    # Pravni dokumenti više ne tvrde da samouslužno brisanje ne postoji.
    for ruta in ("/security", "/bezbednosni-list"):
        t = _cist(k, ruta)
        assert "nije izložen kao samouslužno dugme" not in t and "u pripremi" not in t, ruta
        assert "Obriši nalog" in t, ruta


# ═══════════════════════════════════════════════════════════════════════════
# 4. POST /api/support/poruka — istinit ishod
# ═══════════════════════════════════════════════════════════════════════════

_IP = itertools.count(1)
KORISNIK = {"user_id": "11111111-1111-1111-1111-111111111111", "email": "advokat@example.com"}


class _Tabela:
    def __init__(self, padne=False):
        self.padne, self.upisi = padne, []

    def insert(self, red):
        self.upisi.append(red)
        self.citanje = False
        return self

    def select(self, *a, **kw):
        self.citanje = True
        return self

    def order(self, *a, **kw):
        return self

    def limit(self, *a, **kw):
        return self

    def execute(self):
        if getattr(self, "citanje", False):
            return MagicMock(data=list(self.upisi))
        if self.padne:
            raise RuntimeError("baza nedostupna")
        return MagicMock(data=[{"id": "abcdef12-3456-7890-abcd-ef1234567890", **self.upisi[-1]}])


@pytest.fixture()
def podrska():
    """(klijent, tabela, emailovi) — prijavljen KORISNIK, SMTP po izboru testa."""
    tabela = _Tabela()
    poslato = []
    supa = MagicMock()
    supa.table.side_effect = lambda ime: tabela if ime == "support_tickets" else MagicMock()
    api.app.dependency_overrides[get_current_user] = lambda: dict(KORISNIK)
    with patch.object(sp, "_get_supa", return_value=supa):
        yield TestClient(api.app, raise_server_exceptions=False), tabela, poslato
    api.app.dependency_overrides.pop(get_current_user, None)


def _posalji(klijent, **telo):
    return klijent.post("/api/support/poruka", json={"kategorija": "tehnicko", "poruka": "Lista predmeta se ne učitava.", **telo},
                        headers={"X-Forwarded-For": f"198.51.100.{next(_IP) % 250 + 1}"})


def test_bez_prijave_401():
    r = TestClient(api.app).post("/api/support/poruka", json={"poruka": "Ovo je dovoljno dug opis."},
                                 headers={"X-Forwarded-For": "192.0.2.77"})
    assert r.status_code == 401


def test_sacuvano_bez_smtp_je_uspeh_sa_brojem_i_bez_obecanja(podrska):
    klijent, tabela, _ = podrska
    with patch.object(sp, "_SMTP_HOST", ""):
        r = _posalji(klijent)
    assert r.status_code == 200
    o = r.json()
    assert o["ok"] is True and o["sacuvano"] is True and o["obavesteno"] is False and o["broj"] == "abcdef12"
    assert "abcdef12" in o["message"] and "24" not in o["message"]
    assert len(tabela.upisi) == 1


def test_ni_sacuvano_ni_poslato_nije_uspeh(podrska):
    klijent, tabela, _ = podrska
    tabela.padne = True
    with patch.object(sp, "_SMTP_HOST", ""):
        r = _posalji(klijent)
    assert r.status_code == 503
    assert '"ok":true' not in r.text.replace(" ", "")


def test_neuspeo_upis_ali_poslat_email_je_uspeh_bez_broja(podrska):
    klijent, tabela, _ = podrska
    tabela.padne = True
    with patch.object(sp, "_send_support_email", return_value=True):
        r = _posalji(klijent)
    assert r.status_code == 200
    o = r.json()
    assert o["sacuvano"] is False and o["obavesteno"] is True and o["broj"] is None


def test_identitet_je_iz_tokena_a_ne_iz_tela(podrska):
    klijent, tabela, _ = podrska
    with patch.object(sp, "_SMTP_HOST", ""):
        r = _posalji(klijent, user_id="22222222-2222-2222-2222-222222222222", email="napadac@example.com")
    assert r.status_code == 200
    red = tabela.upisi[-1]
    assert red["user_id"] == KORISNIK["user_id"] and red["email"] == KORISNIK["email"]
    assert set(red) == {"user_id", "email", "kategorija", "poruka", "rating", "kontekst"}


def test_nepoznata_kategorija_je_ostalo_a_kratak_opis_422(podrska):
    klijent, tabela, _ = podrska
    with patch.object(sp, "_SMTP_HOST", ""):
        assert _posalji(klijent, kategorija="admin").status_code == 200
        assert tabela.upisi[-1]["kategorija"] == "ostalo"
        assert _posalji(klijent, poruka="kratko").status_code == 422
    assert len(tabela.upisi) == 1


def test_email_escapuje_html_i_ne_dozvoljava_ubacivanje_zaglavlja(monkeypatch):
    uhvaceno = {}

    class _SMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self): pass
        def login(self, *a): pass
        def sendmail(self, od, za, sirovo): uhvaceno["sirovo"] = sirovo

    monkeypatch.setattr(sp, "_SMTP_HOST", "localhost")
    monkeypatch.setattr(sp, "FOUNDER_EMAILS", {"osnivac@example.com"})
    monkeypatch.setattr(sp.smtplib, "SMTP", _SMTP)
    ok = sp._send_support_email(user_email="a@example.com\r\nBcc: strana@example.com", kategorija="ai",
                                poruka="<img src=x onerror=alert(1)> netačan odgovor", kontekst="<b>Predmet</b>",
                                broj="abcdef12-xxxx")
    assert ok is True
    import email as _email
    poruka = _email.message_from_bytes(uhvaceno["sirovo"])
    assert poruka.get_all("Bcc") is None
    # Sirovo zaglavlje sme biti presavijeno (RFC 5322), ali dekodirana vrednost je jedan red.
    import email.header as _hdr
    naslov = str(_hdr.make_header(_hdr.decode_header(poruka["Subject"])))
    odgovor = str(_hdr.make_header(_hdr.decode_header(poruka["Reply-To"])))
    assert not re.search(r"[\r\n]", naslov + odgovor)
    assert "#abcdef12]" in naslov and "Bcc: strana@example.com" in naslov
    html_deo = "".join(p.get_payload(decode=True).decode() for p in poruka.walk() if p.get_content_type() == "text/html")
    assert "<img" not in html_deo and "&lt;b&gt;" in html_deo


def test_neuspeh_smtp_vraca_false(monkeypatch):
    class _Pada:
        def __init__(self, *a, **kw): raise OSError("veza odbijena")

    monkeypatch.setattr(sp, "_SMTP_HOST", "localhost")
    monkeypatch.setattr(sp, "FOUNDER_EMAILS", {"osnivac@example.com"})
    monkeypatch.setattr(sp.smtplib, "SMTP", _Pada)
    assert sp._send_support_email(user_email="a@example.com", kategorija="ostalo", poruka="Dovoljno dug opis.") is False


def test_lista_prijava_samo_za_osnivaca(podrska):
    klijent, _, _ = podrska
    assert klijent.get("/api/support/admin/lista").status_code == 403
    api.app.dependency_overrides[get_current_user] = lambda: {"user_id": "x", "email": next(iter(sp.FOUNDER_EMAILS))}
    assert klijent.get("/api/support/admin/lista").status_code == 200


def test_ponovljen_klik_je_zasticen_idempotencijom():
    from shared.idempotency import je_zasticena
    assert je_zasticena("POST", "/api/support/poruka")


# ═══════════════════════════════════════════════════════════════════════════
# 5. V2 kontrola: šta se šalje i gde se pojavljuje
# ═══════════════════════════════════════════════════════════════════════════

def _v2(put):
    with open(os.path.join(KOREN, "frontend-v2-ng", put), encoding="utf-8") as f:
        return f.read()


def test_v2_kontrola_salje_samo_kategoriju_opis_i_naziv_ekrana():
    js = _v2("src/prijava-problema.js")
    telo = re.search(r"telo: \{([^}]*)\}", js).group(1)
    assert re.findall(r"(\w+):", telo) == ["kategorija", "poruka", "kontekst"]
    for zabranjeno in ("screenshot", "user_id", "localStorage", "innerHTML = poruka", "predmet_id"):
        assert zabranjeno not in js.replace("dugme.innerHTML = '<svg", ""), zabranjeno
    # Kategorije su postojeće kategorije backenda.
    for kljuc in re.findall(r'\["(\w+)", "', js):
        assert kljuc in sp._KATEGORIJE, kljuc
    assert "Sadržaj predmeta, dokumenti, AI odgovori i snimak ekrana se ne prilažu" in js


def test_v2_kontrola_je_samo_u_live_rezimu():
    assert '<script src="src/prijava-problema.js"></script>' in _v2("index.html")
    app = _v2("src/app.js")
    live = app.index("} else if (rt && rezim === rt.LIVE")
    assert app.index("VxPrijavaProblema.napravi") > live
