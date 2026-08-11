# -*- coding: utf-8 -*-
"""
Wave 9 / G2 — matrica failure semantike za `routers/jobs.py::run_in_background`.

Zašto ovaj fajl postoji
-----------------------
`/api/strategija/kompletna-analiza` odgovara HTTP 202 sa `job_id`, a stvarni
posao ide kroz `run_in_background`. Zbog toga je HTTP status odgovora BESKORISAN
kao signal uspeha — sve što korisnik ikada sazna dolazi iz zapisa posla koji
klijent poluje. Ako ijedan neuspeh (provajder pao, timeout, firewall BLOCK,
nema kredita) uspe da završi kao `status="done"` ili da ostavi popunjen
`result`, korisnik dobija lažnu analizu bez ijedne vidljive greške.

Metodologija (namerno)
----------------------
Ovi testovi STVARNO IZVRŠAVAJU `run_in_background` i mere zapis posla posle
izvršavanja. Nijedan test ne čita izvorni kod niti traži imena simbola u njemu.
Razlog je konkretan: u prethodnim sprintovima su tri puta testovi pogodili
KOMENTAR umesto koda (npr. provera „da li se `UsageService.consume` pojavljuje"
pogodila je komentar koji objašnjava njegovo uklanjanje) i prijavili zeleno nad
nepostojećim ponašanjem. Izvršavanje ne može da se prevari komentarom.

Šta ovde NIJE (i zašto)
-----------------------
- Dedupe je već dokazan u `tests/test_p1_charge_on_failure.py`
  (`test_job_dedupe_returns_the_running_job_instead_of_starting_a_second`,
  `test_job_dedupe_does_not_suppress_a_genuinely_different_request`,
  `test_job_dedupe_is_scoped_to_one_user`,
  `test_job_dedupe_releases_once_the_job_finished`,
  `test_create_job_without_a_key_never_dedupes`).
  Ne duplira se ovde; dole postoji samo jedan sanity test koji vezuje dedupe za
  ISHOD posla (posao koji je pao ne sme da zaključa novi pokušaj).
- Otkazivanje posla (cancellation) se ne testira — sistem taj ugovor NEMA.
"""
import asyncio
import json

import pytest
from fastapi import HTTPException

import routers.jobs as jobs
from routers.jobs import create_job, poll_job, run_in_background


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─── Pomoćne funkcije ────────────────────────────────────────────────────────

def _svez_posao(tip: str = "kompletna_analiza", uid: str = "user-1") -> str:
    """Prazan store + jedan nov posao. Store je per-proces, pa se čisti."""
    jobs._jobs.clear()
    return create_job(uid, tip)


async def _pokreni_koji_dize(izuzetak: BaseException) -> dict:
    """Izvrši `run_in_background` nad korutinom koja diže dati izuzetak.

    Vraća STVARAN zapis posla iz store-a posle izvršavanja.
    """
    jid = _svez_posao()

    async def _pada():
        raise izuzetak

    await run_in_background(jid, _pada)
    return jobs._jobs[jid]


def _tvrdi_da_nije_uspeh(zapis: dict, opis: str):
    """Zajednički minimum za SVAKI neuspeh iz matrice.

    Tri odvojene tvrdnje, jer svaka pokriva drugačiji način da neuspeh procuri
    kao uspeh: pogrešan status, lažni `result`, i tiho zaglavljivanje u
    `pending`/`running` (posao koji nikad ne završi izgleda klijentu isto kao
    posao koji još radi — poluje se doveka).
    """
    assert zapis["status"] == "error", f"{opis}: status je {zapis['status']!r}, mora biti 'error'"
    assert zapis["status"] != "done", f"{opis}: neuspeh je proglašen uspehom"
    assert zapis["result"] is None, f"{opis}: result je popunjen ({zapis['result']!r}) na neuspehu"
    assert zapis["status"] not in ("pending", "running"), f"{opis}: posao je ostao zaglavljen"
    assert zapis["error"], f"{opis}: `error` je prazan — korisnik nema šta da vidi"


# ─── 1. Uspeh (kontrola: matrica ne sme da bude zelena zato što sve pada) ─────

@pytest.mark.anyio
async def test_uspeh_daje_done_i_rezultat():
    jid = _svez_posao()

    async def _radi():
        return {"analiza": "gotova"}

    await run_in_background(jid, _radi)
    z = jobs._jobs[jid]
    assert z["status"] == "done"
    assert z["result"] == {"analiza": "gotova"}
    assert z["error"] is None
    assert z["error_status"] is None, "uspeh ne sme da nosi status greške"
    assert z["error_code"] is None


# ─── 2. Tehnički neuspesi ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_provider_failure_ne_postaje_uspeh():
    """Generički izuzetak iz provajdera (OpenAI SDK diže obične Exception-e)."""
    z = await _pokreni_koji_dize(Exception("OpenAI: upstream connect error"))
    _tvrdi_da_nije_uspeh(z, "provider failure")


@pytest.mark.anyio
async def test_timeout_ne_postaje_uspeh():
    """NALAZ (Wave 9): `str(asyncio.TimeoutError())` je PRAZAN string, pa je
    posao završavao sa `error=""`. Status je bio ispravan, ali je klijent
    prikazivao prazan okvir — korisniku je timeout izgledao kao da se ništa
    nije desilo. `_tvrdi_da_nije_uspeh` sada traži neprazan tekst."""
    z = await _pokreni_koji_dize(asyncio.TimeoutError())
    _tvrdi_da_nije_uspeh(z, "timeout")
    assert "TimeoutError" in z["error"], "prazna poruka mora dobiti smislen fallback"


@pytest.mark.anyio
async def test_malformed_odgovor_valueerror_ne_postaje_uspeh():
    z = await _pokreni_koji_dize(ValueError("model vratio ne-JSON"))
    _tvrdi_da_nije_uspeh(z, "malformed (ValueError)")


@pytest.mark.anyio
async def test_malformed_odgovor_jsondecodeerror_ne_postaje_uspeh():
    """`JSONDecodeError` je podklasa `ValueError`, ali se diže iz drugog sloja —
    testira se posebno da promena redosleda `except` grana ne prođe tiho."""
    z = await _pokreni_koji_dize(json.JSONDecodeError("Expecting value", "{{", 0))
    _tvrdi_da_nije_uspeh(z, "malformed (JSONDecodeError)")


@pytest.mark.anyio
async def test_firewall_block_ne_postaje_uspeh():
    """`security/response_firewall.py::ResponseBlocked` — odgovor je odbijen,
    pa je jedini ispravan ishod greška, nikad isporučen sadržaj."""
    from security.response_firewall import ResponseBlocked

    z = await _pokreni_koji_dize(ResponseBlocked("BLOCK: sadržaj je prazan string"))
    _tvrdi_da_nije_uspeh(z, "firewall BLOCK")


@pytest.mark.anyio
async def test_tehnicki_neuspeh_ne_dobija_lazni_poslovni_kod():
    """Negativna kontrola za G1/3: obična greška NE SME da se predstavi kao
    402/429. Da se to desi, korisniku bi se prikazao paywall zbog pada mreže."""
    z = await _pokreni_koji_dize(Exception("connection reset"))
    assert z["error_status"] == 500, "tehnička greška mora imati jednoznačan 500"
    assert z["error_status"] not in (402, 429, 403, 404)
    assert z["error_code"] is None, "mašinski kod se ne sme izmišljati za tehničku grešku"


# ─── 3. Poslovni neuspesi (HTTPException) ────────────────────────────────────

@pytest.mark.anyio
async def test_billing_402_daje_strukturisan_no_credits():
    """Tačan oblik koji diže `routers/strategija.py:588`."""
    z = await _pokreni_koji_dize(HTTPException(
        status_code=402,
        detail={"code": "NO_CREDITS", "message": "Za kompletnu analizu je potrebno 6 kredita, a na raspolaganju 0."},
    ))
    _tvrdi_da_nije_uspeh(z, "billing 402")
    assert z["error_status"] == 402
    assert z["error_code"] == "NO_CREDITS"


@pytest.mark.anyio
async def test_cooldown_429_daje_error_status_429():
    z = await _pokreni_koji_dize(HTTPException(
        status_code=429,
        detail={"code": "COOLDOWN", "message": "Sačekajte pre sledećeg pokušaja."},
    ))
    _tvrdi_da_nije_uspeh(z, "cooldown 429")
    assert z["error_status"] == 429
    assert z["error_code"] == "COOLDOWN"


@pytest.mark.anyio
async def test_ownership_404_daje_error_status_404():
    """Vlasništvo nad predmetom pada unutar posla — `detail` je običan string,
    ne dict. Mora i dalje da nosi status, a `error_code` ostaje None."""
    z = await _pokreni_koji_dize(HTTPException(status_code=404, detail="Predmet nije pronađen."))
    _tvrdi_da_nije_uspeh(z, "ownership 404")
    assert z["error_status"] == 404
    assert z["error_code"] is None


@pytest.mark.anyio
async def test_permission_403_daje_error_status_403():
    z = await _pokreni_koji_dize(HTTPException(
        status_code=403,
        detail={"code": "PLAN_REQUIRED", "message": "Funkcija zahteva PRO tarifu."},
    ))
    _tvrdi_da_nije_uspeh(z, "permission 403")
    assert z["error_status"] == 403
    assert z["error_code"] == "PLAN_REQUIRED"


# ─── 4. Backward compatibility (negativna kontrola protiv restrukturiranja) ──

@pytest.mark.anyio
async def test_backward_compat_error_polje_i_dalje_nosi_tekst_za_402():
    """Postojeći frontend čita ISKLJUČIVO `job.error`. Ako bi neko zamenio to
    polje strukturisanim objektom ili ga uklonio, stari klijent bi na paywall
    slučaju prikazao prazninu — greška bi postala nevidljiva. Ovaj test je
    brava na tom polju, nezavisno od toga što su nova polja dodata."""
    z = await _pokreni_koji_dize(HTTPException(
        status_code=402,
        detail={"code": "NO_CREDITS", "message": "Nemate dovoljno kredita."},
    ))
    assert "error" in z, "polje `error` je uklonjeno — stari frontend je slep"
    assert isinstance(z["error"], str), f"`error` mora ostati string, a ne {type(z['error']).__name__}"
    assert z["error"].strip(), "`error` je prazan string"
    assert "kredita" in z["error"], "`error` ne nosi upotrebljiv ljudski tekst"


@pytest.mark.anyio
async def test_backward_compat_error_tekst_za_ne_dict_detail_je_nepromenjen():
    """Za `detail` koji nije dict format `error`-a mora ostati identičan onome
    pre izmene (`str(exc)`), da nijedan postojeći klijent koji parsira taj
    string ne pukne."""
    exc = HTTPException(status_code=404, detail="Predmet nije pronađen.")
    z = await _pokreni_koji_dize(exc)
    assert z["error"] == str(exc)


# ─── 5. Ugovor koji polling endpoint izlaže frontendu ────────────────────────

@pytest.mark.anyio
async def test_poll_job_izlaze_error_status_i_error_code():
    """Strukturisana polja moraju da stignu DO klijenta, ne samo do store-a.
    Bez ovoga je G1 mrtav kod — frontend nikad ne vidi 402."""
    jid = _svez_posao()

    async def _pada():
        raise HTTPException(status_code=402, detail={"code": "NO_CREDITS", "message": "Nema kredita."})

    await run_in_background(jid, _pada)
    odg = await poll_job(jid, {"user_id": "user-1"})

    assert odg["status"] == "error"
    assert odg["result"] is None
    assert odg["error"] == "Nema kredita."
    assert odg["error_status"] == 402
    assert odg["error_code"] == "NO_CREDITS"


@pytest.mark.anyio
async def test_poll_job_ne_izlaze_polja_greske_na_uspehu():
    jid = _svez_posao()

    async def _radi():
        return {"ok": True}

    await run_in_background(jid, _radi)
    odg = await poll_job(jid, {"user_id": "user-1"})

    assert odg["status"] == "done"
    assert odg["error"] is None
    assert odg["error_status"] is None
    assert odg["error_code"] is None


# ─── 6. Nema zaglavljenog stanja ─────────────────────────────────────────────

@pytest.mark.anyio
@pytest.mark.parametrize("izuzetak", [
    Exception("provider down"),
    asyncio.TimeoutError(),
    ValueError("malformed"),
    HTTPException(status_code=402, detail={"code": "NO_CREDITS", "message": "Nema kredita."}),
    HTTPException(status_code=429, detail={"code": "COOLDOWN", "message": "Sačekajte."}),
])
async def test_pali_posao_nikad_ne_ostaje_pending(izuzetak):
    """Posao zaglavljen u `pending` je najgori ishod: klijent poluje beskonačno,
    a korisnik gleda spinner koji nikad ne stane."""
    z = await _pokreni_koji_dize(izuzetak)
    assert z["status"] == "error"
    assert z["updated_at"] >= z["created_at"], "zapis nije ni dodirnut"


@pytest.mark.anyio
async def test_posao_koji_je_pao_ne_zakljucava_novi_pokusaj():
    """Veza dedupe ↔ ishod. Dedupe (već dokazan u `test_p1_charge_on_failure.py`)
    hvata samo `pending`/`running`; posle greške advokat MORA moći da pokuša
    ponovo, inače ga jedan pad provajdera zaključa do isteka TTL-a."""
    jobs._jobs.clear()

    jid1, reused1 = jobs.create_job_deduped("u1", "kompletna_analiza", dedupe_key="k1")
    assert reused1 is False

    async def _pada():
        raise Exception("provider down")

    await run_in_background(jid1, _pada)
    assert jobs._jobs[jid1]["status"] == "error"

    jid2, reused2 = jobs.create_job_deduped("u1", "kompletna_analiza", dedupe_key="k1")
    assert reused2 is False, "pali posao ne sme da se reciklira kao 'u letu'"
    assert jid2 != jid1
