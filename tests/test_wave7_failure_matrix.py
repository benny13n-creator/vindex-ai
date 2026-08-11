# -*- coding: utf-8 -*-
"""
Wave 7 — failure matrica za skupi strategija posao.

PITANJE NA KOJE OVAJ FAJL ODGOVARA

„Da li timeout / 5xx / malformed response / DB failure mogu postati lažni
uspeh, i da li korisnik može biti naplaćen za posao koji nije isporučen?"

Odgovor se ne izvodi iz koda nego se meri: za svaki tip kvara broji se koliko je
GPT poziva stvarno izvršeno, da li je naplata pozvana, i u kom stanju posao
završava.

UGOVOR KOJI SE PROVERAVA

`routers/strategija.py::_run_analiza` zove `UsageService.consume` TEK POSLE
`asyncio.to_thread(orkestrator...)`. Ako orkestrator digne izuzetak, `consume`
se nikad ne izvrši. To je ugovor „ne naplaćuj ako AI padne" — i on se ovde meri,
a ne pretpostavlja.

`routers/jobs.py::run_in_background` hvata SVAKI izuzetak i upisuje
`status="error"`. Posledica koja je zabeležena kao P1 još u Wave 2: 402 i 429 iz
naplate degradiraju u isti generički string kao i provajderska greška. Ovaj fajl
to MERI i beleži, ne popravlja — semantika greške na 202-putanji je zaseban
nalaz.
"""
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import strategija  # noqa: E402

_OPIS = (
    "Stranka tvrdi da je ugovor raskinut zbog kašnjenja u isporuci, dok protivna strana "
    "osporava osnovanost raskida. Vrednost spora je 4.200.000 dinara, postupak je u prvom "
    "stepenu pred Privrednim sudom, a ročište još nije zakazano."
)


def _ok_odgovor():
    m = MagicMock()
    m.usage = None
    m.model = "gpt-4o"
    poruka = MagicMock()
    poruka.content = json.dumps({"confidence": "SREDNJA", "summary": "ok"})
    poruka.tool_calls = None
    izbor = MagicMock()
    izbor.message = poruka
    m.choices = [izbor]
    return m


class _PadaNaKoraku:
    """Provajder koji uspe N puta pa digne zadati izuzetak."""

    def __init__(self, pada_na, izuzetak):
        self.pada_na = pada_na
        self.izuzetak = izuzetak
        self.pozivi = 0

    def __call__(self, client, **kwargs):
        self.pozivi += 1
        if self.pozivi == self.pada_na:
            raise self.izuzetak
        return _ok_odgovor()


async def _pokreni_posao(provajder):
    """Izvršava STVARNI `_run_analiza` i meri naplatu i ishod.

    Ne testira rutu nego telo posla — tamo se nalazi ugovor o naplati.
    """
    import routers.strategija as rs

    naplate = {"n": 0}

    async def _consume(uid, email, key, **kw):
        naplate["n"] += 1
        return 100

    req = rs.OrkestratorRequest(opis_predmeta=_OPIS)
    bt = MagicMock()
    posao = {}

    def _job(*a, **k):
        return ("job-1", False)

    with patch("shared.deps._get_credits", return_value=999), \
         patch("shared.permissions._is_founder", return_value=False), \
         patch("routers.jobs.create_job_deduped", new=_job), \
         patch("routers.strategija._audit", new=AsyncMock()), \
         patch("routers.strategija._audit_strategija_durably", new=MagicMock()), \
         patch("routers.strategija.UsageService.consume", new=_consume), \
         patch("routers.strategija.log_cost_to_db", new=AsyncMock()), \
         patch("routers.strategija._kanonski_kontekst_blok", new=AsyncMock(return_value="")), \
         patch("strategija._pozovi_strategija_api", side_effect=provajder):
        await rs.post_kompletna_analiza.__wrapped__(
            req=req, request=MagicMock(), background_tasks=bt,
            user={"user_id": "u1", "email": "a@test.rs"},
        )
        # `add_task(run_in_background, jid, _run_analiza)` -- izvrši posao ručno,
        # kroz STVARNI runner, da bi se merilo i njegovo hvatanje izuzetaka.
        from routers.jobs import run_in_background, _jobs
        args = bt.add_task.call_args[0]
        _jobs["job-1"] = {"id": "job-1", "user_id": "u1", "tip": "kompletna_analiza",
                          "status": "pending", "result": None, "error": None,
                          "created_at": 0, "updated_at": 0, "dedupe_key": None}
        await run_in_background("job-1", args[2])
        posao = dict(_jobs["job-1"])

    return {
        "gpt_poziva": getattr(provajder, "pozivi", 0),
        "naplata": naplate["n"],
        "status": posao.get("status"),
        "greska": posao.get("error"),
    }


# ─── F3–F6: GPT pukne na različitim koracima ───────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("korak", [1, 2, 4, 7])
async def test_a_gpt_pad_ne_naplacuje(korak):
    """Ugovor „ne naplaćuj ako AI padne", meren na četiri tačke lanca.

    Ključna tvrdnja nije „posao je error" nego **naplata == 0**. Da se naplata
    dešava pre posla, ovo bi palo na svakom koraku.
    """
    r = await _pokreni_posao(_PadaNaKoraku(korak, RuntimeError("provajder pao")))
    assert r["status"] == "error", f"pad na koraku {korak} je prijavljen kao uspeh"
    assert r["naplata"] == 0, (
        f"NAPLAĆENO uprkos padu na koraku {korak} — korisnik plaća posao koji "
        f"nije isporučen"
    )
    assert r["gpt_poziva"] == korak, (
        f"očekivano {korak} GPT poziva pre pada, izvršeno {r['gpt_poziva']}"
    )


@pytest.mark.asyncio
async def test_ng_uspesan_posao_SE_naplacuje():
    """Negativna kontrola.

    Bez ovoga bi svi testovi iznad prolazili i da se naplata NIKAD ne dešava —
    što bi bio drugi, gori kvar.
    """
    class _Uvek:
        pozivi = 0
        def __call__(self, client, **kwargs):
            self.pozivi += 1
            return _ok_odgovor()

    p = _Uvek()
    r = await _pokreni_posao(p)
    assert r["status"] == "done"
    assert r["naplata"] == 1, "uspešan posao nije naplaćen"
    assert r["gpt_poziva"] == 7


# ─── Provajderske greške različitog tipa ───────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("izuzetak,opis", [
    (TimeoutError("provider timeout"), "timeout"),
    (ConnectionError("connection reset"), "5xx/mreža"),
    (ValueError("neocekivan oblik"), "malformed"),
])
async def test_b_svaki_tip_kvara_daje_error_bez_naplate(izuzetak, opis):
    r = await _pokreni_posao(_PadaNaKoraku(3, izuzetak))
    assert r["status"] == "error", f"{opis} je prijavljen kao uspeh"
    assert r["naplata"] == 0, f"{opis}: naplaćeno bez isporuke"


# ─── MALFORMED ODGOVOR — Response Firewall na živom putu ───────────────────

@pytest.mark.asyncio
async def test_c_prazan_odgovor_obara_posao_a_ne_naplacuje():
    """Response Firewall (Wave 3) blokira prazan odgovor.

    Meri se da blokada NE postaje lažni uspeh i da ne povlači naplatu — dakle
    ponašanje celog posla, ne samo firewall-a.
    """
    class _Prazan:
        pozivi = 0
        def __call__(self, client, **kwargs):
            self.pozivi += 1
            if self.pozivi == 2:
                m = MagicMock()
                m.usage = None
                m.model = "gpt-4o"
                m.choices = []          # firewall: "prazna lista izbora" -> BLOCK
                return m
            return _ok_odgovor()

    r = await _pokreni_posao(_Prazan())
    assert r["status"] == "error"
    assert r["naplata"] == 0
    assert r["gpt_poziva"] == 2


# ─── ZABELEŽEN NALAZ: semantika greške se gubi ─────────────────────────────

@pytest.mark.asyncio
async def test_d_402_degradira_u_genericki_error_ZABELEZENO():
    """MERENJE zatečenog ponašanja — i ISPRAVKA ranije klasifikacije.

    Wave 2 i Wave 6 su ovo prijavili kao „402/429 degradiraju u generički error
    string", uz zaključak da paywall handler ne može da opali. Merenje pokazuje
    da je ta ocena bila PREOŠTRA.

    `run_in_background` (`routers/jobs.py:120`) upisuje `error=str(exc)`, a
    `str(HTTPException(402, {...}))` daje doslovno:

        "402: {'code': 'NO_CREDITS', 'message': 'nema'}"

    Dakle i statusni kod i kod greške PREŽIVE. Informacija se ne gubi — nije
    strukturisana. Frontend (`strat_job_poll`, `static/vindex.js:3530`) prikazuje
    `j.error` sirovo, pa korisnik vidi tehnički string umesto paywall poruke.

    Prava klasifikacija je dakle UX/format, ne gubitak informacije. Ostaje P2, a
    ne P1 kako je ranije zabeleženo. Test fiksira to stanje da bi promena bila
    primetna.
    """
    from fastapi import HTTPException

    class _Pada402:
        pozivi = 0
        def __call__(self, client, **kwargs):
            self.pozivi += 1
            return _ok_odgovor()

    import routers.strategija as rs

    async def _consume_402(uid, email, key, **kw):
        raise HTTPException(status_code=402, detail={"code": "NO_CREDITS", "message": "nema"})

    req = rs.OrkestratorRequest(opis_predmeta=_OPIS)
    bt = MagicMock()
    with patch("shared.deps._get_credits", return_value=999), \
         patch("shared.permissions._is_founder", return_value=False), \
         patch("routers.jobs.create_job_deduped", return_value=("job-2", False)), \
         patch("routers.strategija._audit", new=AsyncMock()), \
         patch("routers.strategija._audit_strategija_durably", new=MagicMock()), \
         patch("routers.strategija.UsageService.consume", new=_consume_402), \
         patch("routers.strategija.log_cost_to_db", new=AsyncMock()), \
         patch("routers.strategija._kanonski_kontekst_blok", new=AsyncMock(return_value="")), \
         patch("strategija._pozovi_strategija_api", side_effect=_Pada402()):
        await rs.post_kompletna_analiza.__wrapped__(
            req=req, request=MagicMock(), background_tasks=bt,
            user={"user_id": "u1", "email": "a@test.rs"},
        )
        from routers.jobs import run_in_background, _jobs
        _jobs["job-2"] = {"id": "job-2", "user_id": "u1", "tip": "kompletna_analiza",
                          "status": "pending", "result": None, "error": None,
                          "created_at": 0, "updated_at": 0, "dedupe_key": None}
        await run_in_background("job-2", bt.add_task.call_args[0][2])
        posao = dict(_jobs["job-2"])

    assert posao["status"] == "error"
    greska = str(posao["error"])

    # ZATEČENO STANJE, izmereno: informacija PREŽIVI, ali kao goli string.
    assert "402" in greska, "statusni kod je izgubljen — to bi bio stvarni P1"
    assert "NO_CREDITS" in greska, "kod greške je izgubljen — to bi bio stvarni P1"

    # Ono što NE postoji: strukturisan oblik koji frontend može da grana.
    assert not isinstance(posao["error"], dict), (
        "greška je sada strukturisana — zameni ovaj test testom koji dokazuje "
        "da paywall handler može da opali, nemoj ga obrisati"
    )
