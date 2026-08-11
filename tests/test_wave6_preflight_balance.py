# -*- coding: utf-8 -*-
"""
Wave 6 — parcijalni uspeh: AI se izvršavao pre provere bilansa.

NALAZ (root cause, iz koda)

`routers/strategija.py::_run_analiza` izvršava svih 8 GPT-4o poziva
(`asyncio.to_thread(orkestrator_kompletna_analiza_sync, ...)`), pa TEK ONDA zove
`UsageService.consume(...)`. Ako korisnik nema dovoljno kredita, `consume` digne
402, `routers/jobs.py:120` (`run_in_background`) to uhvati i upiše
`status="error"` — a AI rad je već obavljen i plaćen provajderu.

`PermissionService.require("strategija")` ovo ne hvata: on proverava TARIFU, ne
bilans. Bilans se prvi put dodiruje tek u `consume`.

POSLEDICA
`professional` korisnik sa 0 kredita mogao je da pokrene 8 GPT-4o poziva, dobije
generičku grešku, i ponovi to do granice rate limita (`10/hour`,
`routers/strategija.py:368`) — osamdeset GPT-4o poziva na sat po nalogu, bez
ijednog naplaćenog kredita. Trošak nosi firma, korisnik ne dobija ništa.

Ovo je „parcijalni uspeh" iz misije: AI uspe → rezultat postoji → naplata pukne.
Važniji slučaj od običnog HTTP 500, jer sistem ostaje u stanju gde je novac
potrošen a ništa nije isporučeno.

ŠTA POPRAVKA JESTE, A ŠTA NIJE

JESTE: troškovna kapija ispred skupog posla.
NIJE: zamena za `consume`. Atomični odbitak (`migrations/107::deduct_n_credits`)
ostaje POSLE posla, pa ugovor „ne naplaćuj ako AI padne" ostaje netaknut.

Namerno je TOCTOU-tolerantna — između provere i odbitka bilans se može
promeniti. Jedini izvor istine ostaje atomični odbitak; ovo samo sprečava da se
očigledno neplativ zahtev uopšte pokrene.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_USER = {"user_id": "u-wave6", "email": "advokat@test.rs"}
_CENA = 6  # feature_registry: krediti=1 x credit_multiplier=6 (migracija 069)


async def _pozovi(bilans, *, email=None, founder=False):
    """Poziva rutu sa datim bilansom. Vraća (izuzetak_ili_None, broj_pokrenutih_poslova)."""
    import routers.strategija as rs

    poslovi = {"n": 0}

    def _job(*a, **k):
        poslovi["n"] += 1
        return ("job-1", False)

    req = rs.OrkestratorRequest(opis_predmeta="X" * 150)
    korisnik = dict(_USER, email=email or _USER["email"])
    bt = MagicMock()

    with patch("shared.deps._get_credits", return_value=bilans), \
         patch("shared.permissions._is_founder", return_value=founder), \
         patch("routers.jobs.create_job_deduped", new=_job), \
         patch("routers.strategija._audit", new=AsyncMock()), \
         patch("routers.strategija._audit_strategija_durably", new=MagicMock()):
        try:
            await rs.post_kompletna_analiza.__wrapped__(
                req=req, request=MagicMock(), background_tasks=bt, user=korisnik,
            )
            return None, poslovi["n"]
        except HTTPException as e:
            return e, poslovi["n"]


# ─── 1. NEDOVOLJAN BILANS ZAUSTAVLJA PRE POSLA ──────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("bilans", [0, 1, 5])
async def test_a_nedovoljan_bilans_ne_pokrece_AI_posao(bilans):
    """Srž Wave 6.

    Ključna tvrdnja nije „vraća 402" nego „posao NIJE pokrenut" — jer je posao
    ono što košta. Da se 402 vraćao a posao ipak kreirao, trošak bi ostao.
    """
    izuzetak, poslova = await _pozovi(bilans)
    assert izuzetak is not None, f"bilans {bilans} < {_CENA} je propušten"
    assert izuzetak.status_code == 402
    assert poslova == 0, (
        f"posao je POKRENUT uprkos bilansu {bilans} — 8 GPT-4o poziva bi se "
        f"izvršilo i naplatilo firmi, a korisnik ne bi dobio ništa"
    )


@pytest.mark.asyncio
async def test_b_poruka_navodi_potrebno_i_raspolozivo():
    """Generička greška ovde nije dovoljna.

    Korisnik mora znati KOLIKO mu nedostaje, inače ne zna ni šta da uradi.
    """
    izuzetak, _ = await _pozovi(2)
    detalj = izuzetak.detail
    assert isinstance(detalj, dict), "402 nosi goli string umesto strukturisanog detalja"
    assert detalj.get("code") == "NO_CREDITS"
    assert str(_CENA) in detalj["message"]
    assert "2" in detalj["message"], "poruka ne navodi raspoloživ bilans"


# ─── 2. NEGATIVNE KONTROLE ──────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("bilans", [6, 7, 100])
async def test_ng_dovoljan_bilans_pokrece_posao(bilans):
    """Bez ovoga bi `test_a` prolazio i da kapija odbija SVE.

    Granica je tačno na ceni: 6 mora proći, 5 ne (v. `test_a`).
    """
    izuzetak, poslova = await _pozovi(bilans)
    assert izuzetak is None, f"bilans {bilans} >= {_CENA} je odbijen"
    assert poslova == 1


@pytest.mark.asyncio
async def test_ng_founder_zaobilazi_kapiju():
    """Founder nema odbitak kredita nigde u sistemu (`shared/usage.py:318`).

    Kapija ne sme biti stroža od postojećeg modela — to bi bila nova politika.
    """
    izuzetak, poslova = await _pozovi(0, founder=True)
    assert izuzetak is None
    assert poslova == 1


@pytest.mark.asyncio
async def test_c_greska_pri_citanju_bilansa_NE_blokira():
    """Svesno fail-OPEN, suprotno od vlasničke kapije — i to je namerno.

    Ovo je troškovna optimizacija, ne bezbednosna kontrola. Atomični odbitak
    posle posla je i dalje autoritativan i uhvatiće nedostatak kredita. Da je
    fail-closed, pad baze bi oborio funkciju koja bi inače radila.
    """
    import routers.strategija as rs

    poslovi = {"n": 0}

    def _job(*a, **k):
        poslovi["n"] += 1
        return ("job-1", False)

    req = rs.OrkestratorRequest(opis_predmeta="X" * 150)
    with patch("shared.deps._get_credits", side_effect=RuntimeError("baza")), \
         patch("shared.permissions._is_founder", return_value=False), \
         patch("routers.jobs.create_job_deduped", new=_job), \
         patch("routers.strategija._audit", new=AsyncMock()), \
         patch("routers.strategija._audit_strategija_durably", new=MagicMock()):
        await rs.post_kompletna_analiza.__wrapped__(
            req=req, request=MagicMock(), background_tasks=MagicMock(), user=dict(_USER),
        )
    assert poslovi["n"] == 1, "greška u čitanju bilansa je oborila analizu"


# ─── 3. UGOVOR SA POSTOJEĆOM NAPLATOM OSTAJE NETAKNUT ──────────────────────

def test_d_consume_i_dalje_stoji_POSLE_AI_posla():
    """Pre-flight ne sme da postane zamena za atomični odbitak.

    Ako bi neko premestio `consume` ispred posla „radi simetrije", izgubio bi se
    ugovor „ne naplaćuj ako AI padne" — koji je zaseban, ranije dokazan
    invarijant (`tests/test_p1_charge_on_failure.py`).
    """
    import inspect
    import re
    import routers.strategija as rs

    # Komentari i docstring se UKLANJAJU pre merenja. Prva verzija ovog testa
    # merila je poziciju `UsageService.consume` u MOM SOPSTVENOM komentaru iznad
    # pre-flight bloka, koji taj naziv pominje objašnjavajući nalaz — pa je
    # zaključila da je odbitak ispred posla. Isti razred greške već je uhvaćen
    # dvaput u ovom programu (P0-D2 `test_b`, Wave 4). Test koji meri tekst nije
    # test koda.
    src = inspect.getsource(rs.post_kompletna_analiza)
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))

    poz_preflight = src.index("_CENA_KOMPLETNE")
    poz_thread = src.index("asyncio.to_thread(")
    poz_consume = src.index("UsageService.consume")

    assert poz_preflight < poz_thread, "pre-flight nije ispred skupog posla"
    assert poz_thread < poz_consume, (
        "atomični odbitak je premešten ISPRED AI posla — time se gubi ugovor "
        "'ne naplaćuj ako AI padne'"
    )
