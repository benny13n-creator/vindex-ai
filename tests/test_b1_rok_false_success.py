# -*- coding: utf-8 -*-
"""
B1 — ROK KOJI NIJE UPISAN NE SME DA SE PRIJAVI KAO USPEH.

ŠTA JE BILO — reprodukovano pre popravke, ne pretpostavljeno

`POST /api/predmeti/{id}/confirm-links` je uzimao `vaznost` iz tela zahteva bez
ijedne provere, sa podrazumevanom vrednošću `"bitan"`:

    "vaznost": rok.get("vaznost", "bitan")          # api.py:6666 (pre)

`predmet_hronologija.vaznost` ima CHECK (`supabase_setup.sql:415`) koji
dozvoljava isključivo `kritičan | važan | informativan`. Sonda produkcije:
52 reda, sve tri šemske vrednosti, **nijedna** `bitan`. INSERT je dakle padao
na 23514, `except` ga je gutao u `logger.warning`, a ruta je svejedno vraćala:

    {"rok_dodat": False, "success": True}

Izmereno na produkcijskoj funkciji, lažni Supabase koji STVARNO primenjuje CHECK:

    ODGOVOR ENDPOINTA : {'rok_dodat': False, 'success': True, ...}
    UPISANO U BAZU    : []
    ODBIJENO CHECK-om : ['bitan']

Frontend (`static/vindex.js::pred_confirmLinks`) je čitao **samo** `d.success`
i ispisivao `✓ Sačuvano.` za rok koji u bazi ne postoji.

UGOVOR KOJI OVI TESTOVI ZAKLJUČAVAJU

    upis uspeo         →  success = True,  rok_dodat = True
    upis pao (CHECK)   →  success = False, rok_dodat = False
    upis pao (bilo šta)→  success = False, rok_dodat = False
    upis vratio 0 redova → isto kao pad (tiše, ali isto)
    rok nije ni tražen →  success = True,  rok_dodat = False   (nepromenjeno)

    NIKAD:  success = True  uz  rok_dodat = False  kad je rok tražen.

ZAŠTO LAŽNI SUPABASE PRIMENJUJE CHECK

Test koji mokuje bazu tako da svaki INSERT prolazi ne bi izmerio ništa — kvar
je nastao baš zato što baza odbija ono što kod šalje. Zato `_Supa` ovde nosi
`_DOZVOLJENE` i diže 23514 na sve van tog skupa, isto kao produkcija.
"""
import asyncio
import os
import sys

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from unittest.mock import patch  # noqa: E402
from starlette.requests import Request as _SReq  # noqa: E402

import api  # noqa: E402

UID = "uid-advokat"
PRED = "pred-1"

# Vrednosti koje CHECK u produkciji STVARNO dozvoljava (supabase_setup.sql:415;
# potvrđeno sondom nad 52 postojeća reda).
_DOZVOLJENE = {"kritičan", "važan", "informativan"}


class _Res:
    def __init__(self, data):
        self.data = data


class _Supa:
    """Lažni Supabase koji STVARNO primenjuje CHECK ograničenje."""

    def __init__(self, *, insert_puca=False, prazan_insert=False):
        self.upisano = []
        self.odbijeno = []
        self._puca = insert_puca
        self._prazan = prazan_insert

    def table(self, ime):
        spolja = self

        class _Q:
            def select(self, *a, **k):
                return self

            def eq(self, *a, **k):
                return self

            def in_(self, *a, **k):
                return self

            def single(self):
                return self

            def maybe_single(self):
                return self

            def insert(self, red):
                if ime == "predmet_hronologija":
                    if spolja._puca:
                        raise RuntimeError("baza nedostupna")
                    v = red.get("vaznost")
                    if v not in _DOZVOLJENE:
                        spolja.odbijeno.append(v)
                        raise RuntimeError(
                            'new row for relation "predmet_hronologija" violates '
                            'check constraint "predmet_hronologija_vaznost_check" '
                            f"(vaznost={v!r})"
                        )
                    if not spolja._prazan:
                        spolja.upisano.append(red)
                self._red = red
                return self

            def execute(self):
                if ime == "predmeti":
                    return _Res({"id": PRED})
                if ime in ("klijenti", "predmet_klijenti"):
                    return _Res([])
                if ime == "predmet_hronologija":
                    # PostgREST vraća upisane redove; prazna lista je stanje
                    # „nijedan red nije upisan".
                    return _Res([] if spolja._prazan else [getattr(self, "_red", {})])
                return _Res([{"id": "x"}])

        return _Q()


def _request():
    return _SReq({
        "type": "http", "method": "POST",
        "path": "/api/predmeti/x/confirm-links",
        "headers": [], "query_string": b"", "client": ("1.2.3.4", 1234),
        "app": api.app, "scheme": "http", "server": ("test", 80), "root_path": "",
    })


def _pozovi(supa, dodaj_rok):
    req = api.ConfirmLinksReq(klijent_ids=[], uloga="stranka", dodaj_rok=dodaj_rok)

    async def _run():
        with patch.object(api, "_get_supa", return_value=supa), \
             patch.object(api, "_audit", new=lambda *a, **k: asyncio.sleep(0)):
            return await api.predmet_confirm_links(
                predmet_id=PRED, req=req, request=_request(),
                user={"user_id": UID, "email": "a@b.rs"},
            )

    return asyncio.run(_run())


# ─── TEST 1 — VALIDAN UPIS ────────────────────────────────────────────────────

def test_1_validan_rok_se_upisuje_i_prijavljuje_kao_uspeh():
    supa = _Supa()
    r = _pozovi(supa, {"naziv": "Žalba na presudu",
                       "datum_iso": "2026-09-01", "vaznost": "važan"})

    assert len(supa.upisano) == 1, "rok nije stigao do baze"
    assert supa.upisano[0]["vaznost"] == "važan"
    assert supa.upisano[0]["dogadjaj"] == "Žalba na presudu"
    assert supa.upisano[0]["datum_iso"] == "2026-09-01"
    assert r["rok_dodat"] is True
    assert r["success"] is True
    assert "rok_greska" not in r


def test_1b_frontend_payload_prolazi_check():
    """Vrednost koju `static/vindex.js` STVARNO šalje mora biti prihvatljiva.

    Ovo je test protiv ponovnog razilaženja rečnika: ako neko vrati `'bitan'`
    u frontend, ovaj test pada. Vrednost se čita iz izvora, ne prepisuje ovde.
    """
    import re
    js = os.path.join(os.path.dirname(__file__), "..", "static", "vindex.js")
    with open(js, encoding="utf-8") as f:
        izvor = f.read()
    m = re.search(r"naziv:\s*rNaziv,\s*datum_iso:\s*rDatum,\s*vaznost:\s*'([^']+)'", izvor)
    assert m, "confirm-card više ne šalje `vaznost` u očekivanom obliku"
    poslato = m.group(1)
    assert poslato in _DOZVOLJENE, (
        f"frontend šalje `vaznost={poslato!r}` koje CHECK odbija — "
        f"dozvoljeno je samo {sorted(_DOZVOLJENE)}"
    )

    supa = _Supa()
    r = _pozovi(supa, {"naziv": "Rok iz dokumenta",
                       "datum_iso": "2026-09-01", "vaznost": poslato})
    assert r["success"] is True and r["rok_dodat"] is True
    assert len(supa.upisano) == 1


# ─── TEST 2 — DB CHECK REJECT ─────────────────────────────────────────────────

def test_2_check_reject_nije_uspeh():
    """Tačan kvar iz B1: `bitan` obara CHECK.

    Posle popravke backend normalizuje nepoznatu vrednost na `informativan`
    (kanonski obrazad iz `predmet_upload_auto_analyze` i `copilot.py`), pa
    upis USPEVA — ali se meri i drugi, važniji slučaj: kad upis stvarno padne,
    odgovor NE SME biti uspeh (v. `test_2b`).
    """
    supa = _Supa()
    r = _pozovi(supa, {"naziv": "Rok", "datum_iso": "2026-09-01",
                       "vaznost": "bitan"})

    # Nijedna vrednost van šeme ne sme stići do baze.
    assert supa.odbijeno == [], f"CHECK je odbio {supa.odbijeno} — vrednost nije normalizovana"
    assert len(supa.upisano) == 1
    assert supa.upisano[0]["vaznost"] in _DOZVOLJENE
    assert r["success"] is True and r["rok_dodat"] is True


def test_2b_kad_baza_ODBIJE_upis_odgovor_nije_uspeh():
    """Sam kvar: red nije upisan → `success` mora biti False.

    Simulira se CHECK rejection nezavisno od `vaznost` normalizacije (npr.
    NOT NULL na `dogadjaj`, FK, buduće ograničenje) — ugovor je isti.
    """
    supa = _Supa(insert_puca=True)
    r = _pozovi(supa, {"naziv": "Žalba", "datum_iso": "2026-09-01",
                       "vaznost": "kritičan"})

    assert supa.upisano == [], "dokaz da red NIJE upisan"
    assert r["rok_dodat"] is False
    assert r["success"] is False, "neuspeo upis prijavljen kao uspeh — B1 je otvoren"
    assert "rok_greska" in r and r["rok_greska"]


# ─── TEST 3 — GENERIČKI DB EXCEPTION ──────────────────────────────────────────

def test_3_genericki_db_izuzetak_nije_uspeh():
    supa = _Supa(insert_puca=True)
    r = _pozovi(supa, {"naziv": "Rok", "datum_iso": "2026-10-01",
                       "vaznost": "informativan"})

    assert supa.upisano == []
    assert r["rok_dodat"] is False
    assert r["success"] is False


def test_3b_prazan_rezultat_upisa_je_neuspeh():
    """0 upisanih redova je isto što i pad — samo tiše."""
    supa = _Supa(prazan_insert=True)
    r = _pozovi(supa, {"naziv": "Rok", "datum_iso": "2026-10-01",
                       "vaznost": "važan"})

    assert supa.upisano == []
    assert r["rok_dodat"] is False
    assert r["success"] is False


# ─── TEST 4 — RESPONSE INVARIANT ──────────────────────────────────────────────

@pytest.mark.parametrize("supa_kw,rok", [
    ({}, {"naziv": "R", "datum_iso": "2026-09-01", "vaznost": "važan"}),
    ({}, {"naziv": "R", "datum_iso": "2026-09-01", "vaznost": "bitan"}),
    ({}, {"naziv": "R", "datum_iso": "2026-09-01"}),
    ({}, {"naziv": "R"}),
    ({"insert_puca": True}, {"naziv": "R", "datum_iso": "2026-09-01", "vaznost": "važan"}),
    ({"insert_puca": True}, {"naziv": "R", "datum_iso": "2026-09-01", "vaznost": "bitan"}),
    ({"prazan_insert": True}, {"naziv": "R", "datum_iso": "2026-09-01", "vaznost": "važan"}),
    ({"prazan_insert": True}, {"naziv": "R", "datum_iso": "2026-09-01", "vaznost": "xyz"}),
])
def test_4_nikad_success_true_uz_rok_dodat_false(supa_kw, rok):
    """Invarijanta preko SVIH putanja rute kad je rok tražen."""
    supa = _Supa(**supa_kw)
    r = _pozovi(supa, rok)

    assert not (r["success"] is True and r["rok_dodat"] is False), (
        f"ZABRANJENO STANJE: success=True uz rok_dodat=False "
        f"(supa={supa_kw}, rok={rok}) → {r}"
    )
    # Ogledalo iste invarijante: uspeh znači da red POSTOJI u bazi.
    assert (r["success"] is True) == (len(supa.upisano) == 1)


def test_4b_bez_trazenog_roka_ponasanje_je_nepromenjeno():
    """Regresiona brava: ruta bez `dodaj_rok` mora ostati uspeh.

    Bez ovoga bi `success = rok_dodat` oborilo svaki poziv koji rok i ne traži
    (povezivanje klijenata je zasebna, ranija funkcija ove rute).
    """
    supa = _Supa()
    r = _pozovi(supa, None)

    assert r["rok_dodat"] is False
    assert r["success"] is True
    assert "rok_greska" not in r
