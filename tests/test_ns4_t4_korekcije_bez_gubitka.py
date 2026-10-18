# -*- coding: utf-8 -*-
"""Night Sprint IV — Task 4: agregacija korekcija advokata u stil profil bez gubitka i bez tuđih redova.

Zatečeno (`routers/corrections.py::_update_style_profile`):
  1. greška upisa `firm_style_profile` se samo loguje, a korekcije se ipak označe `processed=True` — izgubljene
     za profil zauvek (ponovni pokušaj ih više ne vidi);
  2. potvrda je `UPDATE … WHERE kancelarija_id=X AND processed=false` — označava SVE neobrađene redove kancelarije,
     i one preko `.limit(50)` i one upisane posle čitanja serije, iako nijedan od njih nije analiziran.

Stvarna funkcija, baza u memoriji (`tests/ns005_harness.Baza`), bez mreže i bez modela (< 20 redova → bez GPT-a).
"""
import asyncio

import pytest

import tests.ns005_harness as h5
from routers import corrections as C

K = "kkkkkkkk-0000-4000-8000-00000000000a"
K2 = "kkkkkkkk-0000-4000-8000-00000000000b"


class _BazaSaKvarom(h5.Baza):
    """Upis (insert/update/upsert) u `pad_upis` tabele pada; čitanje radi. `posle_citanja` se izvrši odmah posle
    PRVOG čitanja zadate tabele — model konkurentnog upisa između čitanja serije i potvrde."""

    def __init__(self, tabele):
        super().__init__(tabele)
        self.pad_upis = {}
        self.posle_citanja = {}

    def table(self, ime):
        baza = self
        upit = super().table(ime)
        izvorni = upit.execute

        def execute():
            vrsta = upit.radnja[0]
            if vrsta in ("insert", "update", "upsert") and ime in baza.pad_upis:
                raise baza.pad_upis[ime]
            rez = izvorni()
            if vrsta == "select" and ime in baza.posle_citanja:
                baza.posle_citanja.pop(ime)(baza)
            return rez
        upit.execute = execute
        return upit


def _kor(i, kanc=K, processed=False, tip="stil"):
    return {"id": f"c-{kanc[-1]}-{i:03d}", "kancelarija_id": kanc, "user_id": "uid-A", "context_type": "drafting",
            "original_output": "Predlažemo da sud usvoji tužbeni zahtev u celosti.",
            "edited_output": "Predlažemo da sud usvoji tužbeni zahtev.\n- prvo\n- drugo",
            "tip_dokumenta": "tuzba", "tip_korekcije": tip, "processed": processed}


def _baza(redovi, profil=None):
    return _BazaSaKvarom({"ai_corrections": redovi, "firm_style_profile": list(profil or [])})


def _obradjeni(baza):
    return {r["id"] for r in baza.tabele["ai_corrections"] if r.get("processed")}


def _pokreni(baza, kanc=K):
    return asyncio.run(C._update_style_profile(kanc, baza))


def test_neuspeh_upisa_profila_ne_oznacava_korekcije_obradjenim():
    baza = _baza([_kor(i) for i in range(3)])
    baza.pad_upis["firm_style_profile"] = Exception("db down")
    rez = _pokreni(baza)
    assert _obradjeni(baza) == set(), "korekcije označene obrađenim iako profil nije upisan"
    assert rez["ok"] is False, "neuspeh upisa profila prijavljen kao uspeh"
    # ponovni pokušaj (baza se oporavila) obrađuje iste tri korekcije — ništa nije izgubljeno
    baza.pad_upis.clear()
    rez2 = _pokreni(baza)
    assert rez2["ok"] is True and rez2["processed"] == 3 and len(_obradjeni(baza)) == 3
    assert baza.tabele["firm_style_profile"][0]["korekcija_count"] == 3


def test_potvrda_samo_za_tacno_analiziranu_seriju_preko_limita(monkeypatch):
    """≥ 20 redova pokreće model za opis stila — ovde model pada: korekcije se i dalje obrade (bez opisa)."""
    async def _model_pada(*a, **k):
        raise RuntimeError("model nedostupan")
    monkeypatch.setattr(C, "_pozovi_correction_api", _model_pada)
    baza = _baza([_kor(i) for i in range(60)])
    rez = _pokreni(baza)
    assert rez["processed"] == 50
    assert len(_obradjeni(baza)) == 50, "potvrđeni i redovi preko limita koji nisu analizirani"
    assert baza.tabele["firm_style_profile"][0]["korekcija_count"] == 50
    rez2 = _pokreni(baza)
    assert rez2["processed"] == 10 and len(_obradjeni(baza)) == 60
    assert baza.tabele["firm_style_profile"][0]["korekcija_count"] == 60, "ponovni prolaz dvaput broji"


def test_korekcija_upisana_posle_citanja_serije_ostaje_neobradjena():
    baza = _baza([_kor(i) for i in range(3)])
    kasna = _kor(99)
    baza.posle_citanja["ai_corrections"] = lambda b: b.tabele["ai_corrections"].append(dict(kasna))
    rez = _pokreni(baza)
    assert rez["processed"] == 3
    assert kasna["id"] not in _obradjeni(baza), "kasna korekcija potvrđena bez analize"
    assert _pokreni(baza)["processed"] == 1 and kasna["id"] in _obradjeni(baza)


def test_ponovni_prolaz_ne_broji_vec_potvrdjene():
    baza = _baza([_kor(i) for i in range(4)])
    _pokreni(baza)
    rez = _pokreni(baza)
    assert rez == {"ok": True, "processed": 0}
    assert baza.tabele["firm_style_profile"][0]["korekcija_count"] == 4


def test_druga_kancelarija_netaknuta():
    baza = _baza([_kor(i) for i in range(3)] + [_kor(i, kanc=K2) for i in range(2)])
    _pokreni(baza)
    tudje = [r for r in baza.tabele["ai_corrections"] if r["kancelarija_id"] == K2]
    assert all(not r["processed"] for r in tudje)
    assert [p["kancelarija_id"] for p in baza.tabele["firm_style_profile"]] == [K]


def test_neuspeh_potvrde_se_prijavljuje():
    baza = _baza([_kor(i) for i in range(2)])
    baza.pad_upis["ai_corrections"] = Exception("db down")
    rez = _pokreni(baza)
    assert rez["ok"] is False, "profil upisan, potvrda pala — ne sme se prijaviti kao čist uspeh"


def test_original_korekcije_nikad_ne_menja():
    redovi = [_kor(i) for i in range(2)]
    baza = _baza(redovi)
    _pokreni(baza)
    for r, o in zip(baza.tabele["ai_corrections"], redovi):
        assert (r["original_output"], r["edited_output"]) == (o["original_output"], o["edited_output"])
