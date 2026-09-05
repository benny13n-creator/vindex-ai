# -*- coding: utf-8 -*-
"""
Z016 GATE A — GLOBALNA LJUSKA + DANAS.

Sta ovi testovi cuvaju, a sto se iz koda ne vidi:

  1. DVE SEMANTICKE KLASE SE NE MESAJU.
     Potvrdjena obaveza (rociste, ili rok sa `stanje_odluke=CONFIRMED`) i
     nepotvrdjen predlog nikad ne stoje u istom redu ni istom statusu.
     `test_potvrdjen_rok_je_obaveza` i
     `test_dokazan_predlog_ide_u_ZA_PROVERU_nikad_medju_obaveze` obaraju to.

  1b. NEDOKAZIV RED NE ULAZI (fail-closed).
     `predmet_hronologija` nema kolonu o VRSTI reda; `_klasifikuj_dogadjaj` ima
     catch-all `return "rok_dokument"`, a `izvor` je `LEGACY_UNKNOWN` na svih 55
     redova u celoj tabeli. Bez dokaza red se ne prikazuje ni kao obaveza ni kao
     predlog. `test_nedokaziv_red_NE_ULAZI_u_danas` i `test_akter_sa_AI_nije_dokaz`.

  2. ISTI ROK SE NE SME POJAVITI DVAPUT.
     Kalendar i kandidati citaju ISTU tabelu. Ako se iz kalendara uzme bilo sta
     osim rocista, svaka obaveza se udvostrucuje.

  3. NEIZGRADJEN PROSTOR NE POSTOJI U NAVIGACIJI.
     Ne kao onemogucen, ne kao „uskoro". `test_neizgradjen_prostor_ne_postoji`.

  4. `od` NA `/api/rokovi/kandidati` NE SME PROMENITI ZATECENO PONASANJE.
     Bez parametra opseg mora poceti danas, tacno kao pre. Parametar postoji
     zato sto istekao rok inace uopste nije dohvatljiv sa stanjem odluke —
     dokazano: bez njega `dana=7` na ovom nalogu vraca 0, sa njim 1.
"""
import json
import os
import shutil
import subprocess
import sys
import textwrap
from datetime import date, timedelta

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret-longer-than-32-chars")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

KOREN = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V2 = os.path.join(KOREN, "v2").replace("\\", "/")
sys.path.insert(0, KOREN)

node = shutil.which("node")


# ═══════════════════════════════════════════════════════════════════════════
# Backend — `od` na /api/rokovi/kandidati
# ═══════════════════════════════════════════════════════════════════════════

class _Upit:
    """Belezi granice opsega koje ruta postavi, bez dodira sa mrezom."""

    def __init__(self, trag):
        self.trag = trag

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def gte(self, kolona, vrednost):
        self.trag["gte"] = vrednost
        return self

    def lte(self, kolona, vrednost):
        self.trag["lte"] = vrednost
        return self

    def execute(self):
        return type("R", (), {"data": []})()


def _req():
    """Rate limiter zahteva PRAVI starlette Request; ovo je najmanji koji prolazi."""
    from unittest.mock import MagicMock
    from starlette.requests import Request as StarletteRequest

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return StarletteRequest(
        scope={"type": "http", "method": "GET", "path": "/api/rokovi/kandidati",
               "headers": [], "query_string": b"", "app": MagicMock(),
               "state": MagicMock(), "client": ("127.0.0.1", 1234)},
        receive=receive,
    )


def _pozovi_kandidate(**kw):
    import asyncio
    from unittest.mock import patch
    import routers.rok_odluka as ro

    trag = {}
    supa = type("S", (), {"table": lambda self, ime: _Upit(trag)})()
    with patch.object(ro, "_get_supa", lambda: supa), \
         patch.object(ro, "odluke", lambda ids: {}):
        odgovor = asyncio.run(ro.kandidati(
            request=_req(), user={"user_id": "u1"}, **kw))
    return trag, odgovor


def test_bez_od_opseg_pocinje_danas():
    """Zateceno ponasanje mora ostati bajt u bajt isto."""
    trag, _ = _pozovi_kandidate(dana=7)
    assert trag["gte"] == date.today().isoformat()
    assert trag["lte"] == (date.today() + timedelta(days=7)).isoformat()


def test_od_pomera_samo_pocetak_unazad():
    od = (date.today() - timedelta(days=90)).isoformat()
    trag, _ = _pozovi_kandidate(dana=7, od=od)
    assert trag["gte"] == od
    # Gornja granica se i dalje racuna od DANAS — `od` ne sme tiho produziti
    # pogled u buducnost.
    assert trag["lte"] == (date.today() + timedelta(days=7)).isoformat()


def test_od_u_buducnosti_se_skracuje_na_kraj_opsega():
    od = (date.today() + timedelta(days=400)).isoformat()
    trag, _ = _pozovi_kandidate(dana=7, od=od)
    assert trag["gte"] == trag["lte"]


def test_neispravan_od_je_422():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _pozovi_kandidate(dana=7, od="15.06.2026")
    assert e.value.status_code == 422
    assert "YYYY-MM-DD" in e.value.detail


def test_predugacak_opseg_je_422():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _pozovi_kandidate(dana=7, od=(date.today() - timedelta(days=400)).isoformat())
    assert e.value.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Dokument i asseti
# ═══════════════════════════════════════════════════════════════════════════

def test_dokument_ucitava_danas_stil():
    from fastapi.testclient import TestClient
    import api
    k = TestClient(api.app)
    html = k.get("/app-v2").text
    assert "/styles/danas.css" in html
    import re
    baza = "/v2/@" + re.findall(r"/v2/@([A-Za-z0-9._-]+)/", html)[0]
    for f in ["/styles/danas.css", "/domain/danas.js", "/domain/spaces.js",
              "/features/danas/api.js", "/features/danas/view.js"]:
        assert k.get(baza + f).status_code == 200, f


def test_child_rute_prostora_serviraju_isti_dokument():
    from fastapi.testclient import TestClient
    import api
    k = TestClient(api.app)
    a = k.get("/app-v2/danas")
    b = k.get("/app-v2/predmeti")
    assert a.status_code == b.status_code == 200
    assert a.text == b.text


# ═══════════════════════════════════════════════════════════════════════════
# Domen (izvrseno u Node-u)
# ═══════════════════════════════════════════════════════════════════════════

nodemark = pytest.mark.skipif(node is None, reason="node nije dostupan")


def _js(telo: str, dodaj_izvor: str = ""):
    """`dodaj_izvor` privremeno proširuje allow-listu provenijencije, da bi se
    ponašanje klase B moglo dokazati PRE nego što backend počne da je upisuje."""
    prosiri = f'D.IZVOR_DOKAZUJE_PREDLOG.push("{dodaj_izvor}");' if dodaj_izvor else ""
    skripta = textwrap.dedent(f"""
        import * as D from "file:///{V2}/domain/danas.js";
        import * as S from "file:///{V2}/domain/spaces.js";
        {prosiri}
        const rezultat = (() => {{ {telo} }})();
        process.stdout.write(JSON.stringify(rezultat));
    """)
    p = subprocess.run([node, "--input-type=module", "-e", skripta],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


ROK = """{ id:"r1", predmet_id:"p1", dogadjaj:"Rok za odgovor na tuzbu",
          datum_iso: DAN, vaznost:"kritičan", akter:"Pipeline (AI)",
          stanje_odluke: STANJE }"""


@nodemark
def test_nedokaziv_red_NE_ULAZI_u_danas():
    """Fail-closed: red koji se ne moze dokazati kao predlog roka ne ulazi.

    `predmet_hronologija` nema kolonu o VRSTI reda, a `izvor` je
    `LEGACY_UNKNOWN` na svih 55 redova u celoj tabeli. Pogadjanje po tekstu ili
    po `akter` uvuklo bi u Danas istorijske cinjenice predmeta kao rokove —
    mereno: u prozoru od 365 dana 45 od 47 redova su cinjenice, ne rokovi."""
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const k = { rokovi: [{ id:"r1", predmet_id:"p1", dogadjaj:"Kraj zaposlenja tuzioca",
                  datum_iso:"2026-09-06", akter:"Zaposleni Marko", izvor:"LEGACY_UNKNOWN",
                  stanje_odluke:"UNCONFIRMED" }] };
      const s = D.sastavi({ kandidati: k, kalendar: { dogadjaji: [] } }, sada);
      return { ukupno: s.ukupno, obaveza: s.obaveza, provera: s.zaProveru.length,
               nedokazivo: s.nedokazivo };
    """)
    assert r["ukupno"] == 0
    assert r["provera"] == 0
    assert r["nedokazivo"] == 1, "nedokaziv red mora biti prebrojan, ne precutan"


@nodemark
def test_akter_sa_AI_nije_dokaz():
    """`akter` je slobodan tekst. Pogadjanje po njemu je zabranjeno."""
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const k = { rokovi: [{ id:"r1", predmet_id:"p1", dogadjaj:"Rok",
                  datum_iso:"2026-09-06", akter:"Genome (AI)", izvor:"LEGACY_UNKNOWN",
                  stanje_odluke:"UNCONFIRMED" }] };
      return D.sastavi({ kandidati: k, kalendar: { dogadjaji: [] } }, sada).zaProveru.length;
    """)
    assert r == 0


@nodemark
def test_dokazan_predlog_ide_u_ZA_PROVERU_nikad_medju_obaveze():
    """Kada backend pocne da dokazuje provenijenciju, red ulazi — u klasu B."""
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const k = { rokovi: [{ id:"r1", predmet_id:"p1", dogadjaj:"Rok za odgovor",
                  datum_iso:"2026-09-06", izvor:"DOKAZ_TEST", stanje_odluke:"UNCONFIRMED" }] };
      const s = D.sastavi({ kandidati: k, kalendar: { dogadjaji: [] } }, sada);
      return { obaveza: s.obaveza, provera: s.zaProveru.length,
               klasa: s.zaProveru[0] && s.zaProveru[0].klasa,
               naziv: s.zaProveru[0] && s.zaProveru[0].vrstaNaziv,
               nedokazivo: s.nedokazivo };
    """, dodaj_izvor="DOKAZ_TEST")
    assert r["obaveza"] == 0, "predlog NIKAD ne sme uci medju potvrdjene obaveze"
    assert r["provera"] == 1
    assert r["klasa"] == "provera"
    assert r["naziv"] == "Predlog roka"
    assert r["nedokazivo"] == 0


@nodemark
def test_potvrdjen_rok_je_obaveza():
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const k = { rokovi: [{ id:"r1", predmet_id:"p1", dogadjaj:"Rok za odgovor",
                  datum_iso:"2026-09-06", izvor:"LEGACY_UNKNOWN", stanje_odluke:"CONFIRMED" }] };
      const s = D.sastavi({ kandidati: k, kalendar: { dogadjaji: [] } }, sada);
      return { obaveza: s.obaveza, provera: s.zaProveru.length,
               klasa: s.grupe[0].stavke[0].klasa, grupa: s.grupe[0].kljuc };
    """)
    assert r["obaveza"] == 1 and r["provera"] == 0
    assert r["klasa"] == "obaveza"
    assert r["grupa"] == "sutra"


@nodemark
def test_odbijen_predlog_ne_ulazi_i_nije_nedokaziv():
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const k = { rokovi: [{ id:"a", predmet_id:"p", dogadjaj:"X",
                  datum_iso:"2026-09-06", stanje_odluke:"REJECTED" }] };
      const s = D.sastavi({ kandidati: k, kalendar: { dogadjaji: [] } }, sada);
      return { ukupno: s.ukupno, nedokazivo: s.nedokazivo };
    """)
    assert r["ukupno"] == 0
    assert r["nedokazivo"] == 0


@nodemark
def test_kalendarski_rokovi_se_odbacuju():
    """Kalendar i kandidati citaju istu tabelu — bez ovog filtera svaka
    obaveza bi se pojavila dvaput, i to jednom BEZ stanja odluke."""
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const k = { rokovi: [{ id:"r1", predmet_id:"p1", dogadjaj:"Rok za odgovor",
                  datum_iso:"2026-09-06", stanje_odluke:"CONFIRMED" }] };
      const c = { dogadjaji: [
        { tip:"rok_dokument", datum:"2026-09-06", predmet_id:"p1",
          predmet_naziv:"Predmet A", naslov:"⚠️ Rok za odgovor", detalji:{} },
        { tip:"napomena", datum:"2026-09-06", predmet_id:"p1", naslov:"🗒 Beleska", detalji:{} },
        { tip:"rociste", datum:"2026-09-06", vreme:"09:30", predmet_id:"p1",
          predmet_naziv:"Predmet A", detalji:{ id:"h1", sud:"Osnovni sud u Nišu", sudnica:"12" } }] };
      const s = D.sastavi({ kandidati: k, kalendar: c }, sada);
      return { ukupno: s.ukupno, vrste: s.grupe.flatMap(g => g.stavke.map(x => x.vrsta)) };
    """)
    assert r["ukupno"] == 2, "rok iz kalendara je udvostrucio obavezu"
    assert sorted(r["vrste"]) == ["rociste", "rok"]


@nodemark
def test_naziv_predmeta_dolazi_iz_kalendara():
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const k = { rokovi: [{ id:"r1", predmet_id:"p1", dogadjaj:"Rok",
                  datum_iso:"2026-09-06", stanje_odluke:"CONFIRMED" }] };
      const c = { dogadjaji: [{ tip:"rociste", datum:"2026-09-09", predmet_id:"p1",
                  predmet_naziv:"Marković protiv Delta", detalji:{} }] };
      return D.sastavi({ kandidati: k, kalendar: c }, sada).grupe[0].stavke[0].predmet;
    """)
    assert r == "Marković protiv Delta"


@nodemark
def test_ukrasni_emoji_se_skida():
    """Emoji je prezentacija koju je izabrao drugi sloj, ne podatak."""
    assert _js('return D.ocistiNaslov("⚠️ Rociste zakazano");') == "Rociste zakazano"
    assert _js('return D.ocistiNaslov("🏛 Ročište — Petrović");') == "Ročište — Petrović"
    assert _js('return D.ocistiNaslov("Rok bez ikone");') == "Rok bez ikone"


@nodemark
@pytest.mark.parametrize("razlika,ocekivano", [
    (-82, "propusteno"), (-1, "propusteno"), (0, "danas"), (1, "sutra"),
    (2, "nedelja"), (7, "nedelja"), (8, None), (400, None),
])
def test_granice_grupa(razlika, ocekivano):
    r = _js(f"return D.grupa({razlika});")
    assert r == ocekivano


@nodemark
def test_dalje_od_sedam_dana_ne_ulazi():
    """Danas je ekran paznje, ne kalendar. Sve dalje od 7 dana ispada."""
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const k = { rokovi: [
        { id:"a", predmet_id:"p", dogadjaj:"blizu", datum_iso:"2026-09-10", stanje_odluke:"CONFIRMED" },
        { id:"b", predmet_id:"p", dogadjaj:"daleko", datum_iso:"2026-09-15", stanje_odluke:"CONFIRMED" }] };
      const s = D.sastavi({ kandidati: k, kalendar: { dogadjaji: [] } }, sada);
      return s.grupe.flatMap(g => g.stavke.map(x => x.opis));
    """)
    assert r == ["blizu"]


@nodemark
def test_degradiran_izvor_se_prijavljuje():
    """Delimican pad NIKAD ne sme izgledati kao prazan ekran."""
    assert _js("""return D.sastavi({ kandidati:{rokovi:[]},
        kalendar:{dogadjaji:[], degraded_sources:["rocista"]} }, new Date()).degradirano;""") is True
    assert _js("""return D.sastavi({ kandidati:{rokovi:[], __palo:true},
        kalendar:{dogadjaji:[]} }, new Date()).degradirano;""") is True
    assert _js("""return D.sastavi({ kandidati:{rokovi:[]},
        kalendar:{dogadjaji:[], degraded_sources:[]} }, new Date()).degradirano;""") is False


@nodemark
def test_odseceno_se_prijavljuje():
    assert _js("""return D.sastavi({ kandidati:{rokovi:[], odseceno:true},
        kalendar:{dogadjaji:[]} }, new Date()).odseceno;""") is True


@nodemark
def test_rociste_je_obaveza_bez_modela_potvrde():
    """Rociste je zakazan dogadjaj iz druge tabele — model potvrde se na njega
    ne primenjuje i ne sme se glumiti."""
    r = _js("""
      const sada = new Date(2026, 8, 5);
      const c = { dogadjaji: [{ tip:"rociste", datum:"2026-09-06", vreme:"09:30",
                  predmet_id:"p1", predmet_naziv:"P", detalji:{ id:"h1", sud:"Viši sud", sudnica:"3" } }] };
      const s = D.sastavi({ kandidati:{rokovi:[]}, kalendar:c }, sada);
      return { ...s.grupe[0].stavke[0], obaveza: s.obaveza, provera: s.zaProveru.length };
    """)
    assert r["obaveza"] == 1 and r["provera"] == 0
    assert r["klasa"] == "obaveza"
    assert r["vrstaNaziv"] == "Ročište"
    assert r["opis"] == "Viši sud, 3"
    assert r["vreme"] == "09:30"


@nodemark
@pytest.mark.parametrize("razlika,tekst", [
    (0, "danas"), (1, "sutra"), (-1, "juče"), (-82, "pre 82 dana"), (3, "za 3 dana"),
])
def test_kada_tekst(razlika, tekst):
    assert _js(f"return D.kadaTekst({razlika});") == tekst


# ── Prostori ───────────────────────────────────────────────────────────────

@nodemark
def test_neizgradjen_prostor_ne_postoji():
    r = _js("""return S.vidljiviProstori(["danas","predmeti"]).map(p => p.kljuc);""")
    assert r == ["danas", "predmeti"]
    assert "znanje" not in r and "kancelarija" not in r


@nodemark
def test_prostor_bez_prava_ne_postoji():
    r = _js("""return S.vidljiviProstori(
        ["danas","predmeti","kancelarija"], k => k !== "kancelarija").map(p => p.kljuc);""")
    assert r == ["danas", "predmeti"]


@nodemark
def test_redosled_prostora_je_vlasnicki():
    r = _js("""return S.PROSTORI.map(p => p.kljuc);""")
    assert r == ["danas", "predmeti", "znanje", "kancelarija", "uskladjenost"]
