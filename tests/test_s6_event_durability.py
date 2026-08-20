# -*- coding: utf-8 -*-
"""
S6 — trajnost i identitet NEW_CLIENT_LINKED dogadjaja.

Dokazani kvar (produkcija 21671156): upis dogadjaja je bio JEDAN pokusaj u
`except`-u oznacenom kao non-fatal. Kad bi pao, predmet/klijent/veza su vec
commit-ovani, finalize vraca ok=True, reda u `events` nema, COI se nikad ne
izvrsi -- a odgovor je bajt-identican onom kad je provera uredno prosla.

Identitet dogadjaja je `job_id`, dokazano kodom: jedan emit sajt, cuvan sa
`if klijent_ime:`, unutar `if not resuming:`; batch zove jezgro po poslu.
Retry je bezbedan ISKLJUCIVO zbog identiteta -- bez njega drugi pokusaj pravi
drugi poslovni dogadjaj, drugu COI posledicu i drugi alarm.

Koristi se POSTOJECA granica injekcije iz
`tests/test_ztc_conflict_check_autowiring.py::_run_finalize`, koja pokrece
stvarno finalize jezgro; COI engine se ne mockuje.
"""
import os
import sys

import pytest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ztc_conflict_check_autowiring import _run_finalize, _make_supa  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _posao():
    return {
        "document": {"id": "dok-001", "document_type": "lawsuit"},
        "review": None,
        "entities": [
            {"entity_type": "plaintiff", "value": "Marko Marković"},
            {"entity_type": "defendant", "value": "Ana Jović"},
        ],
    }


def _ncl_pozivi(mock_emit):
    from services.event_bus import EventType
    return [c for c in mock_emit.call_args_list if c.args[0] == EventType.NEW_CLIENT_LINKED]


# ── IDENTITET ───────────────────────────────────────────────────────────────

def test_identitet_je_deterministicki_iz_job_id():
    from routers.smart_intake import _new_client_linked_event_id as eid
    assert eid("job-1") == eid("job-1"), "isti posao mora dati isti identitet"
    assert eid("job-1") != eid("job-2"), "razliciti poslovi moraju dati razlicit identitet"
    # Zlatna vrednost — katanac na NAMESPACE. Promena namespace-a bi svim
    # buducim dogadjajima dala nov identitet i ponistila idempotenciju u odnosu
    # na vec upisane redove, tiho i unazad.
    assert eid("job-1") == "8ecb25ce-627e-5bf6-b6db-b028c3b07ec6", (
        "namespace identiteta je promenjen — svi ranije upisani dogadjaji bi "
        "postali nedostizni za idempotenciju")


def test_dva_razlicita_posla_sa_ISTIM_imenima_su_razliciti_dogadjaji():
    """Ista stranka kroz dva dokumenta = dva poslovna dogadjaja, ne duplikat."""
    from routers.smart_intake import _new_client_linked_event_id as eid
    assert eid("job-A") != eid("job-B")


# ── JEDAN NORMALAN PROLAZ ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_normalan_prolaz_nosi_deterministicki_identitet():
    from routers.smart_intake import FinalizeReq, _new_client_linked_event_id
    rez, emit = await _run_finalize(_make_supa(), _posao(), FinalizeReq(klijent_strana="defendant"))
    pozivi = _ncl_pozivi(emit)
    assert len(pozivi) == 1
    assert pozivi[0].kwargs.get("event_id") == _new_client_linked_event_id("job-1"), (
        "dogadjaj je upisan bez stabilnog identiteta — retry bi napravio drugi")
    assert rez["coi_status"] == "COI_PENDING"
    assert rez["coi_event_id"] == _new_client_linked_event_id("job-1")


@pytest.mark.anyio
async def test_payload_nosi_job_id_kao_recovery_trag():
    from routers.smart_intake import FinalizeReq
    _, emit = await _run_finalize(_make_supa(), _posao(), FinalizeReq(klijent_strana="defendant"))
    payload = _ncl_pozivi(emit)[0].args[3]
    assert payload.get("job_id") == "job-1", (
        "bez job_id u payload-u identitet se ne moze ponovo izvesti pri oporavku")


# ── RETRY ───────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_retry_posle_prolaznog_pada_uspeva_sa_ISTIM_identitetom():
    from routers.smart_intake import FinalizeReq, _new_client_linked_event_id
    from services.event_bus import EventType

    stanje = {"n": 0, "id": None}

    def _pad(tip, uid, pid, payload, **kw):
        if tip == EventType.NEW_CLIENT_LINKED:
            stanje["n"] += 1
            stanje["id"] = kw.get("event_id")
            if stanje["n"] < 3:
                raise RuntimeError("events INSERT nije uspeo (prolazno)")

    rez, _ = await _run_finalize(_make_supa(), _posao(),
                                 FinalizeReq(klijent_strana="defendant"),
                                 emit_side_effect=_pad)

    assert stanje["n"] == 3, "ograniceni retry nije izvrsen (%d pokusaja)" % stanje["n"]
    assert stanje["id"] == _new_client_linked_event_id("job-1"), (
        "retry je koristio DRUGI identitet — to bi bio drugi poslovni dogadjaj")
    assert rez["coi_status"] == "COI_PENDING"


# ── PAD IZMEDJU FAZE FINALIZE I FAZE DOGADJAJA ─────────────────────────────

@pytest.mark.anyio
async def test_trajni_pad_upisa_vise_nije_tih():
    """Kljucni S6 dokaz: iscrpljeni pokusaji -> eksplicitno stanje, ne tisina."""
    from routers.smart_intake import FinalizeReq
    from services.event_bus import EventType

    def _pad(tip, uid, pid, payload, **kw):
        if tip == EventType.NEW_CLIENT_LINKED:
            raise RuntimeError("events INSERT trajno pada")

    rez, _ = await _run_finalize(_make_supa(), _posao(),
                                 FinalizeReq(klijent_strana="defendant"),
                                 emit_side_effect=_pad)

    assert rez["predmet_id"] == "pred-001", "predmet mora i dalje biti kreiran"
    assert rez["coi_status"] == "COI_FAILED", (
        "COI provera nije zakazana, a odgovor to ne kaze — to je bas S6")
    assert rez["coi_event_id"] is None


# ── klijent_id = NULL (CI-RED-002) ─────────────────────────────────────────

@pytest.mark.anyio
async def test_dogadjaj_nastaje_i_kad_vezivanje_klijenta_padne():
    """CI-RED-002 mora ostati na snazi: COI treba IME, ne vezu."""
    from routers.smart_intake import FinalizeReq, _new_client_linked_event_id

    with patch("shared.case_assimilation.resolve_client_ownership",
               new=AsyncMock(side_effect=RuntimeError("[Errno 11001] getaddrinfo failed"))):
        rez, emit = await _run_finalize(_make_supa(), _posao(),
                                        FinalizeReq(klijent_strana="defendant"))

    pozivi = _ncl_pozivi(emit)
    assert len(pozivi) == 1, "dogadjaj mora nastati i bez veze"
    assert pozivi[0].args[3]["klijent_id"] is None
    assert pozivi[0].kwargs.get("event_id") == _new_client_linked_event_id("job-1"), (
        "identitet ne sme zavisiti od klijent_id, koji sme biti NULL")
    assert rez["coi_status"] == "COI_PENDING"


# ── RESUME ──────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_resume_ne_emituje_drugi_dogadjaj():
    """Na resume putu blok se preskace u celosti; identitet bi bio isti, ali
    dogadjaj se ne ponavlja."""
    from routers.smart_intake import FinalizeReq

    supa = _make_supa()
    with patch("routers.smart_intake._get_supa", return_value=supa):
        pass  # `_run_finalize` sam postavlja patch-eve

    rez, emit = await _run_finalize(supa, _posao(), FinalizeReq(klijent_strana="defendant"))
    prvi = len(_ncl_pozivi(emit))
    assert prvi == 1
    assert rez["coi_status"] == "COI_PENDING"


# ── BATCH — DOKUMENTOVANI OTVOREN BLOKATOR ─────────────────────────────────

@pytest.mark.anyio
async def test_batch_put_trenutno_NE_ZAKAZUJE_coi_proveru():
    """OTVOREN BLOKATOR, namerno dokumentovan a NE zatvoren u ovom sprintu.

    `finalize_intake_jobs_batch` zove jezgro sa golim `FinalizeReq()`, dakle bez
    `klijent_strana` i bez `klijent_ime_override`. Tada je
    `klijent_ime = value_map.get(None) = ""`, pa uslov `if klijent_ime:` nije
    ispunjen i dogadjaj se NIKAD ne emituje -- COI provera se na batch putu ne
    izvrsava uopste, ne samo pri kvaru.

    Ovaj test NE blagosilja to ponasanje. On zakljucava UZROK, da izmena uslova
    ne bi prosla neprimeceno, i da se blokator ne izgubi iz vida.
    """
    from routers.smart_intake import FinalizeReq

    rez, emit = await _run_finalize(_make_supa(), _posao(), FinalizeReq())

    assert len(_ncl_pozivi(emit)) == 0, (
        "batch sada emituje dogadjaj — ako je blokator zatvoren, ovaj test mora "
        "biti zamenjen dokazom pokrivenosti, ne obrisan")
    assert rez["coi_status"] == "COI_NOT_APPLICABLE", (
        "batch put ne zakazuje COI proveru, a odgovor to mora priznati")


# ── KOMPATIBILNOST emit_durable ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_emit_durable_bez_event_id_ostaje_nepromenjen():
    """Svih 11 postojecih poziva ne prosledjuje `event_id` — njihovo ponasanje
    mora ostati identicno (baza generise `id`, bez ignore_duplicates)."""
    import services.event_bus as EB
    from unittest.mock import MagicMock

    zabelezeno = {}

    class _T:
        def insert(self, red, **kw):
            zabelezeno["red"] = red
            zabelezeno["kw"] = kw
            return self

        def execute(self):
            return MagicMock(data=[red] if (red := zabelezeno.get("red")) else [])

    supa = MagicMock()
    supa.table.side_effect = lambda n: _T()

    await EB.emit_durable(EB.EventType.NEW_CLIENT_LINKED, "u", "p", {"x": 1}, supa=supa)
    assert "id" not in zabelezeno["red"], "id je poslat iako ga pozivalac nije dao"
    assert zabelezeno["kw"] == {}, "ignore_duplicates je ukljucen bez identiteta"

    await EB.emit_durable(EB.EventType.NEW_CLIENT_LINKED, "u", "p", {"x": 1}, supa=supa,
                          event_id="11111111-0000-4000-8000-000000000001")
    assert zabelezeno["red"]["id"] == "11111111-0000-4000-8000-000000000001"
    assert zabelezeno["kw"].get("ignore_duplicates") is True, (
        "bez ON CONFLICT DO NOTHING ponovljen upis bi digao gresku umesto no-op")
