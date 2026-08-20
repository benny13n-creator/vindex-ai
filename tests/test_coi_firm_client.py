# -*- coding: utf-8 -*-
"""
COI — KLIJENT KOJI JE PRAVNO LICE (firma).

Nadjeno izvrsavanjem STVARNOG toka nad produkcijom `05c1042d`, ne testom:
advokat ima klijenta `firma="Druga firma doo"` vezanog za predmet ulogom
`stranka`; upit o protivnoj strani `"Druga firma doo"` — doslovno isto ime —
vraca NO_CONFLICT. Advokat ne dobija upozorenje da tuzi sopstvenog klijenta.

Zasto suita od 6153 testa ovo nije uhvatila: sve postojece COI karakterizacije
koriste FIZICKA LICA (ime + prezime). Pravno lice je drugi oblik podatka —
naziv stoji u `firma`, `prezime` je prazno — i taj oblik nije bio pokriven.

Testovi ispod idu kroz `_run_conflict_check`, dakle kroz istu funkciju koju
zove `POST /api/intake/conflict-check`, i mere `status_provere`/`has_blocker` —
polja na kojima Intake Wizard zaustavlja tok.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_UID = "aaaa0000-0000-4000-8000-00000000000a"
_KID = "bbbb0000-0000-4000-8000-00000000000b"
_PID = "cccc0000-0000-4000-8000-00000000000c"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _supa(ime="", prezime="", firma="", uloga="stranka", tuzilac="", tuzeni=""):
    """Dvojnik Supabase-a sa JEDNIM klijentom vezanim za JEDAN predmet.

    `uloga` mora biti iz `_CLIENT_ROLES`/`_OPPOSING_ROLES` — proizvoljna
    vrednost tiho ne bi proizvela nijedan nalaz i test bi lazno prolazio.
    """
    klijent = {"id": _KID, "ime": ime, "prezime": prezime, "firma": firma}
    veza = {"klijent_id": _KID, "predmet_id": _PID, "uloga_klijenta": uloga}
    predmet = {"id": _PID, "naziv": "Sintetički predmet",
               "tuzilac": tuzilac, "tuzeni": tuzeni}

    mock = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "klijenti":
            t.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = [klijent]
        elif name == "predmet_klijenti":
            t.select.return_value.eq.return_value.execute.return_value.data = [veza]
            t.select.return_value.in_.return_value.execute.return_value.data = [veza]
        elif name == "predmeti":
            t.select.return_value.eq.return_value.execute.return_value.data = [predmet]
        else:
            t.select.return_value.eq.return_value.execute.return_value.data = []
        return t

    mock.table.side_effect = _table
    return mock


async def _proveri(supa, novi_ime="Novi Klijent", novi_firma="", protivna=""):
    import routers.intake as intake
    with patch.object(intake, "_get_supa", return_value=supa):
        return await intake._run_conflict_check(_UID, novi_ime, novi_firma, protivna, "")


# ── A. Klijent je firma; protivna strana je ISTA firma ──────────────────────

@pytest.mark.anyio
async def test_A_ista_firma_mora_biti_sukob():
    """Doslovna reprodukcija produkcionog kvara. Pada na `05c1042d`."""
    rez = await _proveri(_supa(ime="Druga", firma="Druga firma doo"),
                         protivna="Druga firma doo")
    assert rez["status_provere"] == "CONFLICT_FOUND", (
        "protivna strana je doslovno ime sopstvenog klijenta, a sistem kaze "
        f"{rez['status_provere']!r} — propusten sukob")
    assert rez["has_blocker"] is True, "Intake Wizard bi pustio advokata dalje"


@pytest.mark.anyio
async def test_A2_ista_firma_druga_forma_pravnog_nastavka():
    """`d.o.o.` naspram `doo` — isti subjekt, druga pisana forma."""
    rez = await _proveri(_supa(ime="Druga", firma="Druga firma doo"),
                         protivna="Druga firma d.o.o.")
    assert rez["has_blocker"] is True


@pytest.mark.anyio
async def test_A3_klijent_firma_bez_ime_polja():
    """Neki zapisi imaju SAMO `firma`, `ime`/`prezime` prazni."""
    rez = await _proveri(_supa(ime="", prezime="", firma="Druga firma doo"),
                         protivna="Druga firma doo")
    assert rez["has_blocker"] is True, (
        "klijent bez `ime`/`prezime` se uopste ne poredi po firmi")


# ── B. Razlicite firme — ne sme biti sukoba ─────────────────────────────────

@pytest.mark.anyio
async def test_B_razlicita_firma_nije_sukob():
    rez = await _proveri(_supa(ime="Druga", firma="Druga firma doo"),
                         protivna="Treća firma doo")
    assert rez["status_provere"] == "NO_CONFLICT"
    assert rez["has_blocker"] is False


# ── C. Zastita od laznog pozitiva zbog zajednicke reci ─────────────────────

@pytest.mark.anyio
async def test_C_zajednicka_rec_nije_sukob():
    """"Firma doo" deli rec sa "Druga firma doo" ali nije isti subjekt.

    Ovo je bag zbog kog je `05c1042d` i nastao — ne sme se vratiti.
    """
    rez = await _proveri(_supa(ime="Druga", firma="Druga firma doo"),
                         protivna="Firma doo")
    assert rez["status_provere"] == "NO_CONFLICT", "vracen stari supstring bag"
    assert rez["has_blocker"] is False


# ── D. Fizicko lice — postojece ponasanje mora ostati zeleno ───────────────

@pytest.mark.anyio
async def test_D_fizicko_lice_isti_covek_ostaje_sukob():
    rez = await _proveri(_supa(ime="Petar", prezime="Petrović"),
                         protivna="Petar Petrović")
    assert rez["has_blocker"] is True


@pytest.mark.anyio
async def test_D2_fizicko_lice_drugi_covek_nije_sukob():
    rez = await _proveri(_supa(ime="Petar", prezime="Petrović"),
                         protivna="Milica Jovanović")
    assert rez["status_provere"] == "NO_CONFLICT"
    assert rez["has_blocker"] is False


@pytest.mark.anyio
async def test_D3_fizicko_lice_deljeno_prezime_nije_sukob():
    """Deljeno prezime nije isti covek — zastita od laznog pozitiva."""
    rez = await _proveri(_supa(ime="Petar", prezime="Petrović"),
                         protivna="Milan Petrović")
    assert rez["has_blocker"] is False


# ── E. Mesoviti oblik: novi klijent JE firma ────────────────────────────────

@pytest.mark.anyio
async def test_E_novi_klijent_firma_naspram_klijenta_firme():
    """Grana `q_firma` (linija 633) — nova firma naspram postojece firme.

    Ovaj put je i pre popravke bio ispravan; test cuva da ga ne pokvarimo.
    """
    rez = await _proveri(_supa(ime="Druga", firma="Druga firma doo", uloga="tuzeni"),
                         novi_firma="Druga firma doo", protivna="")
    assert rez["conflict_detected"] is True, (
        "novi klijent je isti subjekt kao postojeca suprotna strana")


@pytest.mark.anyio
async def test_E2_novi_klijent_firma_razlicita_nije_sukob():
    rez = await _proveri(_supa(ime="Druga", firma="Druga firma doo", uloga="tuzeni"),
                         novi_firma="Treća firma doo", protivna="")
    assert rez["status_provere"] == "NO_CONFLICT"


# ── F. Provera nije tiho pala ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_F_provera_je_potpuna():
    """`NO_CONFLICT` sme da znaci samo 'provereno i cisto', nikad 'nije citano'."""
    rez = await _proveri(_supa(ime="Druga", firma="Druga firma doo"),
                         protivna="Treća firma doo")
    assert rez.get("izvori_neuspeh") == [], f"izvor nije procitan: {rez.get('izvori_neuspeh')}"
