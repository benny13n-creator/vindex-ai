# -*- coding: utf-8 -*-
"""
Wave 11 / Z1 — starost `pending` posla kao granica dedupe-a.

ŠTA SE OVDE MERI

`routers/jobs.py::create_job_deduped` ponovo koristi postojeći posao kad mu je
`status in ("pending", "running")`. `pending` je, međutim, stanje koje u
normalnom radu traje milisekunde: `run_in_background` ga prvom linijom
(`routers/jobs.py:177`) prevodi u `running`. Ako pozadinski zadatak nikad ne
bude pokrenut — `background_tasks.add_task` se ne izvrši, worker padne između
`create_job` i `update_job` — red zauvek ostaje `pending`, sve do
`_JOB_TTL_S = 3600`.

Posledica koju je advokat video: svaki identičan zahtev narednih 60 minuta
dobija `202` sa `vec_u_toku: true` i `job_id` posla koji se NIKAD neće završiti.
`static/vindex.js:3628` poluje 180 s, ispiše „Analiza traje duže nego obično…
pokušajte ponovo" (`:3662`), a ponovni pokušaj se vrati na isti mrtav posao.
Nema ni izlaza ni signala.

METOD

Sve se meri IZVRŠAVANJEM `create_job_deduped`, ne čitanjem izvora. Starost se
podešava upisom u `created_at` — istim mehanizmom kojim `tests/test_jobs.py:123`
već meri TTL čišćenje — jer je alternativa čekanje od 181 sekunde po testu.

Nijedan test ovde ne dodiruje mrežu, bazu ni naplatu: `create_job_deduped` je
čista funkcija nad modulskim dict-om.

ŠTA SE OVDE NAMERNO NE DUPLIRA

Dedupe kroz STVARNU rutu `/strategija/kompletna-analiza` (dva zahteva → jedan
posao, jedna naplata, `vec_u_toku: true`) izmeren je u
`tests/test_rc_beta_flows.py::test_d4_ponovljen_zahtev_ne_naplacuje_dvaput`, a
negativna kontrola po `predmet_id`-u u `::test_d5_ng_razlicit_predmet_NIJE_duplikat`.
Oba mere posao u `pending` stanju. Dedupe posla u `running` stanju nije pokriven
nigde — zato `test_a` ispod postoji.
"""
import time

import pytest

import routers.jobs as jobs
from routers.jobs import _JOB_TTL_S, _PENDING_MAX_REUSE_S, create_job_deduped

UID = "11111111-1111-1111-1111-111111111111"
TIP = "kompletna_analiza"
KLJUC = "sha256-istog-zahteva"


@pytest.fixture(autouse=True)
def _cist_store():
    """`jobs._jobs` je modulski globalan i preživljava test — v. Wave 11 / Z2."""
    jobs._jobs.clear()
    yield
    jobs._jobs.clear()


def _ostari(jid: str, sekundi: float) -> None:
    """Pomera nastanak posla u prošlost za `sekundi`.

    `updated_at` se namerno NE dira: granica se meri po `created_at`, isto polje
    po kom radi i `_cleanup` (`routers/jobs.py:31`). Da se meri po `updated_at`,
    posao koji je samo jednom pipnut izgledao bi svež.
    """
    jobs._jobs[jid]["created_at"] = time.time() - sekundi


# ═══════════════════════════════════════════════════════════════════════════
# POSTOJEĆI UGOVOR — dedupe i dalje radi
# ═══════════════════════════════════════════════════════════════════════════

def test_a_dva_identicna_zahteva_dok_posao_STVARNO_radi_daju_jedan_posao():
    """Posao u `running` je posao koji se izvršava — druga analiza je čist gubitak.

    Ovo je jedina tvrdnja o `running` stanju u repou: `test_d4` u
    `tests/test_rc_beta_flows.py` meri isti dedupe, ali nad poslom koji je
    ostao u `pending` (pozadinski zadatak je tamo namerno odložen). Bez ovog
    testa granica iz Z1 mogla bi da se proširi i na `running` a da to ništa ne
    prijavi.
    """
    prvi, ponovo_prvi = create_job_deduped(UID, TIP, dedupe_key=KLJUC)
    assert ponovo_prvi is False, "prvi zahtev je proglašen ponovnom upotrebom"
    jobs.update_job(prvi, "running")

    drugi, reused = create_job_deduped(UID, TIP, dedupe_key=KLJUC)

    assert drugi == prvi, "ponovljen zahtev je pokrenuo DRUGU analizu dok prva radi"
    assert reused is True, (
        "pozivalac ne zna da je posao ponovo upotrebljen, pa će zakazati drugi "
        "pozadinski zadatak — dedupe tada ne postiže ništa"
    )
    assert len(jobs._jobs) == 1, f"u redu je {len(jobs._jobs)} poslova umesto jednog"


# ═══════════════════════════════════════════════════════════════════════════
# Z1 — ZAGLAVLJEN `pending` VIŠE NIJE KANDIDAT
# ═══════════════════════════════════════════════════════════════════════════

def test_b_pending_preko_praga_daje_NOV_posao():
    """Jezgro Z1: posao koji nikad nije prešao u `running` ne sme da blokira retry.

    Bez granice, korisnik je ovde dobijao `job_id` mrtvog posla i to sve do
    `_JOB_TTL_S` (60 minuta) — sat vremena bez ijednog upotrebljivog pokušaja.
    """
    zaglavljen, _ = create_job_deduped(UID, TIP, dedupe_key=KLJUC)
    assert jobs._jobs[zaglavljen]["status"] == "pending"
    _ostari(zaglavljen, _PENDING_MAX_REUSE_S + 1)

    nov, reused = create_job_deduped(UID, TIP, dedupe_key=KLJUC)

    assert nov != zaglavljen, (
        "zahtev je ponovo vezan za posao koji stoji u `pending` preko praga — "
        "korisnik i dalje čeka posao koji se nikad neće izvršiti"
    )
    assert reused is False, (
        "`reused=True` bi značilo da pozivalac NEĆE zakazati pozadinski zadatak "
        "ni za ovaj nov posao — nastao bi drugi mrtav red"
    )
    assert jobs._jobs[nov]["status"] == "pending"
    # Stari posao se ne dira: `_cleanup` je jedini vlasnik brisanja, a korisnik
    # koji još poluje stari `job_id` mora da dobije 404-slobodan odgovor.
    assert zaglavljen in jobs._jobs, "stari posao je obrisan — to nije opseg ove izmene"


def test_c_ng_pending_ISPOD_praga_se_i_dalje_ponovo_koristi():
    """Negativna kontrola bez koje `test_b` ne dokazuje ništa.

    Da je granica postavljena na nulu — ili da je dedupe potpuno uklonjen —
    `test_b` bi prolazio zeleno, a dupli klik bi opet naplaćivao 12 kredita za
    jednu radnju. Starost je namerno POSTAVLJENA blizu praga (a ne ostavljena
    na nuli): time se meri da prag stvarno postoji na izmerenoj vrednosti, ne
    da je posao „nov".
    """
    prvi, _ = create_job_deduped(UID, TIP, dedupe_key=KLJUC)
    _ostari(prvi, _PENDING_MAX_REUSE_S - 30)

    drugi, reused = create_job_deduped(UID, TIP, dedupe_key=KLJUC)

    assert drugi == prvi, (
        f"posao star {_PENDING_MAX_REUSE_S - 30} s (prag je {_PENDING_MAX_REUSE_S} s) "
        f"nije ponovo upotrebljen — dedupe je oslabljen, dupli klik ponovo naplaćuje dvaput"
    )
    assert reused is True
    assert len(jobs._jobs) == 1


def test_d_running_se_ne_prekida_bez_obzira_na_starost():
    """Dokaz da granica NIJE primenjena na posao koji radi.

    Kompletna analiza traje 30–90 s (`routers/strategija.py:556`), ali
    `routers/strategija.py:47` radi eksponencijalni backoff na rate-limit/5xx
    greške provajdera — pa `running` legitimno ume da probije prag. Da granica
    važi i tamo, sistem bi pokrenuo DRUGU kompletnu analizu preko prve i
    naplatio drugih 6 kredita za jednu advokatovu radnju.
    """
    prvi, _ = create_job_deduped(UID, TIP, dedupe_key=KLJUC)
    jobs.update_job(prvi, "running")
    # Znatno preko praga, ali unutar TTL-a — inače bi ga `_cleanup` obrisao i
    # test bi merio čišćenje umesto dedupe-a.
    starost = _PENDING_MAX_REUSE_S * 3
    assert starost < _JOB_TTL_S, "starost mora ostati unutar TTL-a"
    _ostari(prvi, starost)

    drugi, reused = create_job_deduped(UID, TIP, dedupe_key=KLJUC)

    assert drugi == prvi, (
        f"posao koji STVARNO radi ({starost} s u `running`) je prekinut i pokrenuta je "
        f"druga analiza — jedna advokatova radnja naplaćena dvaput"
    )
    assert reused is True
    assert len(jobs._jobs) == 1


# ═══════════════════════════════════════════════════════════════════════════
# ZAVRŠENI POSLOVI — nepromenjeno ponašanje
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ishod", ["done", "error"])
def test_e_zavrsen_posao_ne_blokira_novu_analizu(ishod):
    """Postojeće ponašanje, ovde zaključano da ga Z1 ne pomeri usput.

    `done` i `error` su terminalna stanja: advokat koji ponovo klikne posle
    završene (ili pale) analize traži NOVU analizu. Da se i oni deduplikuju,
    korisnik bi sat vremena dobijao keširan rezultat, a posle greške ne bi imao
    nijedan način da pokuša ponovo.
    """
    prvi, _ = create_job_deduped(UID, TIP, dedupe_key=KLJUC)
    jobs.update_job(prvi, ishod, result={"ok": True} if ishod == "done" else None,
                    error=None if ishod == "done" else "provajder pao")

    drugi, reused = create_job_deduped(UID, TIP, dedupe_key=KLJUC)

    assert drugi != prvi, f"posao u stanju `{ishod}` je ponovo upotrebljen"
    assert reused is False
