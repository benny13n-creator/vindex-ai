# -*- coding: utf-8 -*-
"""
BETA-P1-DEADLINE-TRUTH — ROK KOJI NIJE SAČUVAN NE SME IZGLEDATI KAO SAČUVAN.

ŠTA JE BILO — mereno, ne pretpostavljeno

`routers/rokovi_lanac.py` je računao rokove po ZPP-u **ispravno** i prikazivao
ih advokatu crveno kao `KRITIČAN` uz zakonski osnov. Upis je padao svaki put:

    kod je pisao:   kljucan · normalan · info
    CHECK dozvoljava: kritičan · važan · informativan

U produkciji stoji **52 reda u `predmet_hronologija`, svi sa šemskim vrednostima**
(`kritičan` 17, `važan` 13, `informativan` 22) i **nijedan** sa kod-ovim. Dakle
CHECK važi i **nijedan rok nikad nije upisan ovom putanjom**.

`except` je grešku gutao u `logger.warning`, a odgovor je i dalje glasio
`ok: True` uz `sacuvano_u_predmet: False` — polje koje frontend ne čita.

ZAŠTO NIJE NAPRAVLJENA TABELA `rokovi`

Mandat traži da se prvo rekonstruiše domen. `predmet_hronologija` **jeste**
kanonski vlasnik (10 živih pisaca, FK ka `predmeti`), a `rokovi_lanac` **već
piše u nju**. Ovo dakle nije nedostajući model skladištenja nego **funkcija
čija je polovina upisa pokvarena neusklađenom vrednošću** — kategorija C iz
mandata. Nova tabela bi udvostručila vlasnika pojma „rok".

UGOVOR KOJI OVI TESTOVI ZAKLJUČAVAJU

    upis uspeo   →  200, `sacuvano_u_predmet: True`
    upis pao     →  HTTP greška — nikad 200 sa `ok: True`
    upis prazan  →  isto kao pad (0 redova je isto što i neuspeh, samo tiše)
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import routers.rokovi_lanac as rl  # noqa: E402

UID = "uid-advokat"
PRED = "pred-1"

# Vrednosti koje CHECK u produkciji STVARNO dozvoljava (izmereno na 52 reda).
_DOZVOLJENE = {"kritičan", "važan", "informativan"}


class _Supa:
    """Lažni Supabase koji STVARNO primenjuje CHECK ograničenje."""

    def __init__(self, predmet_postoji=True, insert_puca=False, prazan_insert=False):
        self.upisano = []
        self._p, self._puca, self._prazan = predmet_postoji, insert_puca, prazan_insert

    def table(self, ime):
        spolja = self

        class _Q:
            def __init__(self):
                self._upis = None       # None = ovo je SELECT, ne INSERT

            def select(self, *a, **k):
                return self

            def eq(self, *a, **k):
                return self

            def maybe_single(self):
                return self

            def insert(self, redovi):
                if spolja._puca:
                    raise RuntimeError("baza nedostupna")
                for r in redovi:
                    v = r.get("vaznost")
                    if v not in _DOZVOLJENE:
                        # Tačno ono što produkcija radi: 23514 check violation.
                        raise RuntimeError(
                            f"new row violates check constraint: vaznost={v!r}")
                # `prazan_insert` = PostgREST je vratio 0 redova (npr. RLS je
                # tiho odbio upis). Red NIJE u bazi — zato se ne beleži ni ovde.
                if spolja._prazan:
                    self._upis = []
                else:
                    spolja.upisano.extend(redovi)
                    self._upis = list(redovi)
                return self

            def execute(self):
                if self._upis is not None:
                    return MagicMock(data=self._upis)
                return MagicMock(data={"id": PRED, "naziv": "Predmet"}
                                 if spolja._p else None)
        return _Q()


def _pozovi(supa, predmet_id=PRED):
    body = rl.LanacReq(tip_dogadjaja="dostava_resenja",
                       datum_pocetka="2026-06-01", predmet_id=predmet_id)
    with patch.object(rl, "_get_supa", return_value=supa):
        return asyncio.run(rl.post_rokovi_lanac.__wrapped__(
            body, MagicMock(), {"user_id": UID, "email": "a@a.rs"}))


# ═══════════════════════════════════════════════════════════════════════════
# 1. SRŽ — VREDNOSTI MORAJU PROĆI CHECK
# ═══════════════════════════════════════════════════════════════════════════

def test_rok_se_STVARNO_upisuje():
    """NAJVAŽNIJI TEST U FAJLU.

    Lažni Supabase primenjuje isti CHECK kao produkcija. Pre popravke bi ovaj
    upis pao — kao što je i padao svaki put u stvarnosti.
    """
    supa = _Supa()
    rez = _pozovi(supa)
    assert rez["sacuvano_u_predmet"] is True
    assert supa.upisano, "nijedan rok nije upisan"


def test_sve_mapirane_vaznosti_prolaze_CHECK():
    """Brava nad uzrokom: svaka vrednost koju kod ume da napiše mora biti
    dozvoljena. Bez ovoga bi jedna nova kategorija tiho vratila kvar."""
    for kod_vrednost in rl._VAZNOST_HRON.values():
        assert kod_vrednost in _DOZVOLJENE, (
            f"kod piše {kod_vrednost!r}, CHECK dozvoljava samo {sorted(_DOZVOLJENE)}"
        )


def test_svaka_vaznost_iz_KATALOGA_ima_mapiranje():
    """Druga polovina iste brave, iz suprotnog smera.

    Gornji test čuva da je *slika* mapiranja dozvoljena. Ovaj čuva da je
    *domen* potpun: svaka `vaznost` koju katalog ZPP rokova uopšte proizvodi
    mora imati ključ. Nemapirana vrednost bi pala na fallback `"normalan"`,
    koji CHECK odbija — funkcija bi se ugasila na 503 čim se doda nov tip
    događaja. Ovako to pukne ovde, a ne kod advokata.
    """
    iz_kataloga = {
        r["vaznost"]
        for meta in rl._TIPOVI.values()
        for r in meta["rokovi"]
    }
    nemapirane = iz_kataloga - set(rl._VAZNOST_HRON)
    assert not nemapirane, f"katalog proizvodi nemapirane vrednosti: {nemapirane}"


def test_upisani_redovi_nose_predmet_i_vlasnika():
    supa = _Supa()
    _pozovi(supa)
    for r in supa.upisano:
        assert r["predmet_id"] == PRED
        assert r["user_id"] == UID
        assert r["datum_iso"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. NEUSPEH JE NEUSPEH
# ═══════════════════════════════════════════════════════════════════════════

def test_pad_upisa_vraca_gresku_a_ne_ok_true():
    with pytest.raises(HTTPException) as e:
        _pozovi(_Supa(insert_puca=True))
    assert e.value.status_code >= 500


def test_prazan_upis_je_takodje_neuspeh():
    """0 upisanih redova je isto što i pad — samo tiše."""
    with pytest.raises(HTTPException):
        _pozovi(_Supa(prazan_insert=True))


def test_check_violation_vraca_gresku():
    """Ako bi neko vratio stare vrednosti, advokat mora videti neuspeh."""
    with patch.dict(rl._VAZNOST_HRON, {"kritican": "kljucan"}, clear=False):
        with pytest.raises(HTTPException):
            _pozovi(_Supa())


def test_tudji_predmet_je_404():
    """Autorizacija predmeta ostaje netaknuta."""
    with pytest.raises(HTTPException) as e:
        _pozovi(_Supa(predmet_postoji=False))
    assert e.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 3. BEZ PREDMETA — RAČUNANJE BEZ UPISA OSTAJE LEGITIMNO
# ═══════════════════════════════════════════════════════════════════════════

def test_bez_predmeta_racuna_ali_ne_tvrdi_da_je_sacuvano():
    supa = _Supa()
    rez = _pozovi(supa, predmet_id=None)
    assert rez["sacuvano_u_predmet"] is False
    assert rez["lanac"], "lanac mora biti izračunat i bez predmeta"
    assert supa.upisano == []
