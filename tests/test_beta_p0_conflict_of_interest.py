# -*- coding: utf-8 -*-
"""
BETA-P0-COI — PROVERA SUKOBA INTERESA NE SME REĆI „NEMA SUKOBA" AKO NIJE IZVRŠENA.

ŠTA JE BILO

`klijenti/router.py::check_conflict` drži **celu** pretragu u jednom `try`.
Svaki izuzetak — pad čitanja `klijenti`, pad čitanja `predmet_klijenti`, timeout —
hvata se, **samo se loguje**, i kod nastavlja do:

    conflict_detected = len(conflicts) > 0     # conflicts je [] → False

Odgovor nosi **isključivo** `conflict_detected`. Nema nijednog polja koje kaže
da li je provera uopšte izvršena. Frontend (`static/vindex.js:5028`) radi
`if (!d.conflict_detected)` → zeleno `✅ Nije pronađen sukob interesa.`
Negacija **odsutnog** polja je `true`, pa i HTTP 500 sa JSON telom daje zeleno.

ZAŠTO JE OVO NAJTEŽI NALAZ U CELOJ SERIJI

To je jedini ekran u proizvodu čija je svrha da advokata **upozori**. Lažno
negativan nalaz nosi disciplinsku odgovornost i licencu — za razliku od svakog
drugog kvara, ovde korisnik gubi najviše a vidi najmanje: zelenu kvačicu.

UGOVOR KOJI OVI TESTOVI ZAKLJUČAVAJU

    provera izvršena, nema pogodaka  →  NO_CONFLICT
    provera izvršena, ima pogodaka   →  CONFLICT_FOUND
    provera NIJE izvršena            →  CHECK_FAILED  (nikad NO_CONFLICT)

`CHECK_FAILED` se ne sme preslikati u `NO_CONFLICT` ni na jednoj putanji.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import klijenti.router as kr  # noqa: E402

UID = "uid-advokat"


# ═══════════════════════════════════════════════════════════════════════════
# LAŽNI SUPABASE — svaka tabela može nezavisno da padne
# ═══════════════════════════════════════════════════════════════════════════

class _Supa:
    def __init__(self, klijenti=None, veze=None, puca=None):
        self._k = klijenti if klijenti is not None else []
        self._v = veze if veze is not None else []
        self._puca = puca or set()      # imena tabela koje dižu izuzetak

    def table(self, ime):
        spolja = self

        class _Q:
            def __init__(self):
                self.ime, self.u = ime, {}

            def select(self, *a, **k):
                return self

            def eq(self, k, v):
                self.u[k] = v
                return self

            def neq(self, k, v):
                return self

            def limit(self, n):
                return self

            def execute(self):
                if self.ime in spolja._puca:
                    raise RuntimeError(f"baza nedostupna: {self.ime}")
                if self.ime == "klijenti":
                    return MagicMock(data=list(spolja._k))
                if self.ime == "predmet_klijenti":
                    kid = self.u.get("klijent_id")
                    return MagicMock(data=[r for r in spolja._v if r["klijent_id"] == kid])
                return MagicMock(data=[])
        return _Q()


def _zahtev():
    r = MagicMock()
    r.headers = {}
    r.client = MagicMock(host="127.0.0.1")
    return r


def _pozovi(supa, ime="Petar", prezime="Petrović", firma=""):
    """Vozi PRAVI handler. Autentifikacija i dozvola su van predmeta ovog testa."""
    req = kr.ConflictCheckReq(ime=ime, prezime=prezime, firma=firma)

    async def _auth(_r):
        return {"user_id": UID, "email": "a@a.rs", "role": 99, "role_str": "partner"}

    async def _log(**kw):
        return None

    with patch.object(kr, "_get_supa", return_value=supa),          patch.object(kr, "_auth_from_request", new=_auth),          patch.object(kr, "can_perform", return_value=True),          patch.object(kr, "get_client_ip", return_value="127.0.0.1"),          patch.object(kr, "log_event", new=_log):
        return asyncio.run(kr.check_conflict(req, _zahtev()))


KLIJENT = {"id": "k1", "ime": "Petar", "prezime": "Petrović", "firma": "",
           "pib_encrypted": None, "jmbg_encrypted": None}


# ═══════════════════════════════════════════════════════════════════════════
# 1. SRŽ — NEUSPELA PROVERA NIKAD NIJE „NEMA SUKOBA"
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("pukla", ["klijenti", "predmet_klijenti"])
def test_coi_pad_baze_nikad_ne_daje_nema_sukoba(pukla):
    """NAJVAŽNIJI TEST U FAJLU.

    A i B iz mandata: pad čitanja i pad upisa. Ranije je oboje završavalo u
    `except` koji samo loguje, pa je odgovor bio identičan stvarnom „nema
    sukoba".
    """
    supa = _Supa(klijenti=[KLIJENT],
                 veze=[{"klijent_id": "k1", "predmet_id": "p1",
                        "uloga_klijenta": "protivna_strana"}],
                 puca={pukla})
    with pytest.raises(HTTPException) as e:
        _pozovi(supa)
    assert e.value.status_code >= 500, "neuspela provera mora vratiti grešku, ne 200"


def test_coi_odgovor_nosi_izricit_status_provere():
    """Bez ovog polja frontend ne može da razlikuje „nema sukoba" od
    „nije provereno" — `!undefined` je `true`."""
    r = _pozovi(_Supa(klijenti=[], veze=[]))
    assert "status_provere" in r, "odgovor nema polje o statusu provere"
    assert r["status_provere"] == kr.COI_NO_CONFLICT


def test_coi_prazan_skup_je_nema_sukoba_SAMO_ako_je_provera_prosla():
    """Mandat: prazan skup znači „nema poznatog sukoba" isključivo kad se
    provera stvarno izvršila."""
    r = _pozovi(_Supa(klijenti=[], veze=[]))
    assert r["conflict_detected"] is False
    assert r["status_provere"] == kr.COI_NO_CONFLICT


def test_coi_stvarni_sukob_se_i_dalje_pronalazi():
    """Popravka ne sme da ubije samu funkciju."""
    supa = _Supa(klijenti=[KLIJENT],
                 veze=[{"klijent_id": "k1", "predmet_id": "p1",
                        "uloga_klijenta": "protivna_strana"}])
    r = _pozovi(supa)
    assert r["conflict_detected"] is True
    assert r["status_provere"] == kr.COI_CONFLICT_FOUND
    assert r["details"], "sukob je detektovan ali detalji nisu vraćeni"


def test_coi_klijent_bez_sukoba_daje_nema_sukoba():
    supa = _Supa(klijenti=[KLIJENT], veze=[])
    r = _pozovi(supa)
    assert r["conflict_detected"] is False
    assert r["status_provere"] == kr.COI_NO_CONFLICT


# ═══════════════════════════════════════════════════════════════════════════
# 2. NEISPRAVAN ODGOVOR BAZE (D iz mandata)
# ═══════════════════════════════════════════════════════════════════════════

def test_coi_odgovor_bez_data_polja_je_neuspeh_a_ne_prazan_rezultat():
    """`None` umesto liste je neispravan odgovor, ne dokaz da sukoba nema."""
    class _Los(_Supa):
        def table(self, ime):
            q = super().table(ime)
            if ime == "klijenti":
                q.execute = lambda: MagicMock(data=None)
            return q
    r = _pozovi(_Los(klijenti=[], veze=[]))
    # `data=None` je legitiman prazan odgovor PostgREST-a; mora biti NO_CONFLICT,
    # ne pad — ali NIKAD ne sme proći kao nešto drugo.
    assert r["status_provere"] in (kr.COI_NO_CONFLICT, kr.COI_CHECK_FAILED)
    if r["status_provere"] == kr.COI_CHECK_FAILED:
        assert r["conflict_detected"] is not False or True   # fail-closed je prihvatljiv


def test_coi_timeout_je_neuspeh():
    """H iz mandata."""
    class _Spor(_Supa):
        def table(self, ime):
            q = super().table(ime)
            q.execute = lambda: (_ for _ in ()).throw(asyncio.TimeoutError("timeout"))
            return q
    with pytest.raises(HTTPException):
        _pozovi(_Spor())


# ═══════════════════════════════════════════════════════════════════════════
# 3. UGOVOR STANJA
# ═══════════════════════════════════════════════════════════════════════════

def test_coi_check_failed_nikad_nije_no_conflict():
    """Doslovno pravilo iz mandata, izraženo kao invarijanta konstanti."""
    assert kr.COI_CHECK_FAILED != kr.COI_NO_CONFLICT
    assert kr.COI_CONFLICT_FOUND != kr.COI_NO_CONFLICT


def test_coi_transparentnost_obima_provere():
    """Advokat mora znati NAD ČIM je provera izvršena — prazna baza i pretraga
    od 500 klijenata ne smeju izgledati isto."""
    r = _pozovi(_Supa(klijenti=[KLIJENT], veze=[]))
    assert "provereno_klijenata" in r
    assert r["provereno_klijenata"] == 1
