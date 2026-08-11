# -*- coding: utf-8 -*-
"""
P0-D — granica vlasništva i serijalizacija kanonskog konteksta.

ZAŠTO JE OVO DEO P0-D, A NE ZASEBAN BEZBEDNOSNI ZADATAK

Uvođenje `predmet_id` u `strategija.py` otvara novu putanju čitanja tuđih
podataka. Aplikacija koristi `SUPABASE_SERVICE_KEY` (`shared/deps.py:93`), pa
je RLS zaobiđen i FastAPI autorizacija je JEDINA granica. Integritet konteksta
je zato i vlasnička granica: „potpun kontekst" ne sme značiti „tuđi kontekst".

TRI MERENE ČINJENICE KOJE ODREĐUJU OBLIK KAPIJE

1. `shared/case_context.py:158` lansira svih 7 upita ODJEDNOM, PRE svoje interne
   provere vlasništva (`:402`). Tuđi redovi prođu kroz memoriju procesa iako ne
   dospeju u odgovor. Isti nalaz je već zatvoren u `routers/digital_twin.py:140-152`
   (Lambda Certification 003) izdvajanjem provere da ide prva.

2. `build_case_context` na tuđi id vraća OBIČAN dict sa `"error"`, ne 404. Bez
   kapije bi tuđ `predmet_id` bio nerazlučiv od „nije prosleđen" — advokat bi
   dobio punu analizu naplaćenu 6 kredita, bez signala da je id odbijen.

3. Analiza se izvršava u pozadinskom poslu sa širokim `except Exception`. 404
   dignut unutra ne bi stigao do korisnika.

Zato kapija stoji u ruti, sinhrono, pre kreiranja posla.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.case_context import (  # noqa: E402
    CTX_MARKER_DOKAZ,
    CTX_MARKER_IDENTITET,
    CTX_MARKER_IZVEDENO,
    render_case_context_block,
)

_UID_A = "11111111-1111-1111-1111-111111111111"
_UID_B = "22222222-2222-2222-2222-222222222222"
_PREDMET_OD_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _polje(vrednost):
    """Oblik koji `context_field` proizvodi (`shared/case_context.py:102`)."""
    return {"value": vrednost, "source": "test", "owner": "test",
            "refresh": "test", "timestamp": "2026-08-11T00:00:00+00:00"}


# ─── 1. SERIJALIZATOR ČUVA POREKLO ──────────────────────────────────────────

def test_a_render_razdvaja_dokaz_od_izvedenog():
    """Kriterijum prihvatanja: dovučeno znanje mora ostati razlučivo od dokaza.

    Sva četiri postojeća serijalizatora (`court_predictor.py:195` i dalje) rade
    `.get("value")` i formatiraju samo vrednost — model ne može da razlikuje šta
    je advokat priložio od onoga što je sistem izračunao. Ovaj to razdvaja.
    """
    cc = {
        "case_identity": _polje({"naziv": "Spor ALFA", "tip_postupka": "privredni", "sud": "Privredni sud"}),
        "participants": _polje({"stranka": "DOO Prvi", "protivnik": "DOO Drugi"}),
        "relevant_documents": _polje({"included": [
            {"naziv": "ugovor.pdf", "excerpt": "TEKST-DOKUMENTA-UNIKAT"},
        ]}),
        "risk": _polje({"nivo": "VISOK", "health_score": 41}),
        "contradictions": _polje([{"opis": "KONTRADIKCIJA-UNIKAT"}]),
    }
    blok = render_case_context_block(cc)

    assert CTX_MARKER_IDENTITET in blok
    assert CTX_MARKER_DOKAZ in blok
    assert CTX_MARKER_IZVEDENO in blok
    assert "TEKST-DOKUMENTA-UNIKAT" in blok
    assert "KONTRADIKCIJA-UNIKAT" in blok
    # Dokaz mora biti pod oznakom dokaza, a izračun pod oznakom izvedenog.
    assert blok.index(CTX_MARKER_DOKAZ) < blok.index("TEKST-DOKUMENTA-UNIKAT")
    assert blok.index(CTX_MARKER_IZVEDENO) < blok.index("KONTRADIKCIJA-UNIKAT")
    assert blok.index("TEKST-DOKUMENTA-UNIKAT") < blok.index(CTX_MARKER_IZVEDENO), (
        "izračun sistema se pomešao sa dokaznim materijalom"
    )


@pytest.mark.parametrize("ulaz", [None, {}, {"error": "predmet_not_found"}])
def test_b_render_praznog_konteksta_vraca_prazno(ulaz):
    """`error` dict NIJE kontekst. Mora dati prazan string, ne oznaku bez sadržaja.

    Ovo je tačan oblik koji `build_case_context:403` vraća za tuđi/nepostojeći
    predmet. Da vraća bilo šta drugo, model bi dobio naslov sekcije bez sadržaja
    i popunio ga pretpostavkom.
    """
    assert render_case_context_block(ulaz) == ""


def test_c_render_bez_dokumenata_ne_pravi_praznu_sekciju():
    cc = {"case_identity": _polje({"naziv": "Spor BETA"}),
          "relevant_documents": _polje({"included": []})}
    blok = render_case_context_block(cc)
    assert CTX_MARKER_DOKAZ not in blok
    assert "Spor BETA" in blok


def test_d_render_postuje_budzet_po_dokumentu():
    cc = {"relevant_documents": _polje({"included": [
        {"naziv": "veliki.pdf", "excerpt": "X" * 5000},
    ]})}
    blok = render_case_context_block(cc, doc_budget=100)
    assert "[…]" in blok
    assert len(blok) < 400, "budžet po dokumentu se ne poštuje"


def test_e_render_ne_pada_na_nepotpunom_kontekstu():
    """`_fetch_raw` je fail-soft (`:219-230`) — polja mogu nedostajati."""
    for cc in ({"case_identity": _polje(None)},
               {"relevant_documents": _polje({})},
               {"risk": _polje({}), "contradictions": _polje(None)},
               {"deadlines": _polje([{"nema_datum": True}])}):
        render_case_context_block(cc)   # ne sme dići izuzetak


# ─── 2. VLASNIČKA KAPIJA ────────────────────────────────────────────────────

class _VlasnickiUpit:
    """Mock koji STVARNO sprovodi i `id` i `user_id` filter.

    Obrazac iz `tests/test_tau002_case_context.py:386` — jedini mock u repou
    koji ne no-op-uje `user_id`. Standardni `_FakeQuery` u tom fajlu eksplicitno
    ignoriše sve osim `id`, pa bi test vlasništva sa njim prolazio lažno.
    """

    def __init__(self, red):
        self._red = red
        self._f = {}

    def select(self, *a, **k):
        return self

    def eq(self, polje, vrednost):
        self._f[polje] = vrednost
        return self

    def maybe_single(self):
        return self

    def execute(self):
        r = self._red
        ok = (r is not None
              and r.get("id") == self._f.get("id")
              and r.get("user_id") == self._f.get("user_id"))
        return MagicMock(data=r if ok else None)


def _supa_sa_predmetom_od_A():
    supa = MagicMock()
    supa.table.side_effect = lambda ime: _VlasnickiUpit(
        {"id": _PREDMET_OD_A, "user_id": _UID_A} if ime == "predmeti" else None
    )
    return supa


@pytest.mark.asyncio
async def test_f_tudji_predmet_id_daje_404():
    """Korisnik B ne sme dobiti kontekst predmeta korisnika A.

    Ovo je jedini test u repou koji dokazuje odbijanje TUĐEG (a ne nepostojećeg)
    `predmet_id`-a na ovoj putanji. `tests/test_tau002_case_context.py:148` testira
    samo nepostojeći predmet, i to mockom koji `user_id` filter ignoriše.
    """
    from routers.copilot_ambient import _proveri_vlasnistvo_predmeta
    with patch("routers.copilot_ambient._get_supa", return_value=_supa_sa_predmetom_od_A()):
        with pytest.raises(HTTPException) as e:
            await _proveri_vlasnistvo_predmeta(_PREDMET_OD_A, _UID_B)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_ng_sopstveni_predmet_prolazi():
    """Negativna kontrola: kapija ne sme odbijati sve.

    Bez ovoga bi `test_f` prolazio i da helper bezuslovno diže 404.
    """
    from routers.copilot_ambient import _proveri_vlasnistvo_predmeta
    with patch("routers.copilot_ambient._get_supa", return_value=_supa_sa_predmetom_od_A()):
        await _proveri_vlasnistvo_predmeta(_PREDMET_OD_A, _UID_A)   # ne sme dići


# ─── 3. RUTA ZOVE KAPIJU PRE POSLA ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_g_ruta_proverava_vlasnistvo_pre_kreiranja_posla():
    """Redosled je bitniji od postojanja provere.

    Da kapija stoji posle `create_job_deduped`, tuđi id bi već pokrenuo posao i
    naplatu pre nego što bi bio odbijen.
    """
    import routers.strategija as rs

    redosled = []

    async def _lazna_kapija(pid, uid):
        redosled.append("kapija")
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    def _lazni_job(*a, **k):
        redosled.append("job")
        return ("job-1", False)

    req = rs.OrkestratorRequest(opis_predmeta="X" * 150, predmet_id=_PREDMET_OD_A)
    # `__wrapped__` zaobilazi `@limiter.limit`, koji traži pravi
    # `starlette.requests.Request`. Testira se logika rute, ne rate-limit.
    ruta = rs.post_kompletna_analiza.__wrapped__
    with patch("routers.copilot_ambient._proveri_vlasnistvo_predmeta", new=_lazna_kapija), \
         patch("routers.jobs.create_job_deduped", new=_lazni_job), \
         patch("routers.strategija._audit", new=AsyncMock()), \
         patch("routers.strategija._audit_strategija_durably", new=MagicMock()):
        with pytest.raises(HTTPException) as e:
            await ruta(
                req=req, request=MagicMock(), background_tasks=MagicMock(),
                user={"user_id": _UID_B, "email": "b@test.rs"},
            )
    assert e.value.status_code == 404
    assert redosled == ["kapija"], (
        f"posao je pokrenut uprkos odbijenom predmet_id-u: {redosled}"
    )


def test_h_predmet_id_ulazi_u_dedupe_kljuc():
    """Bez toga bi dve analize istog opisa nad RAZLIČITIM predmetima bile
    proglašene duplikatom, pa bi druga vratila rezultat prvog — a kontekst je
    sada različit. Dedupe bi tiho vratio analizu pogrešnog predmeta."""
    import inspect
    import routers.strategija as rs
    src = inspect.getsource(rs.post_kompletna_analiza)
    # Sidro mora biti dodela, ne prvo pojavljivanje niza -- `_dedupe` se prvi
    # put javlja u importu `create_job_deduped`, 40 linija ranije.
    tacka = src.index("_dedupe = _hashlib")
    assert "req.predmet_id" in src[tacka:tacka + 700], (
        "predmet_id ne učestvuje u dedupe ključu"
    )
