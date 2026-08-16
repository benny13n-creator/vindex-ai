# -*- coding: utf-8 -*-
"""
NIGHT STABILIZATION 001 / FAZA 1 — KLIJENT ↔ PREDMET.

ŠTA JE PALO U STVARNOM RUNTIME-U (mereno pravim HTTP pozivima, pravi Supabase
ES256 tokeni, prava baza, jednokratni nalozi):

1. `POST /klijenti` → **HTTP 500**, `column klijenti.created_at does not exist`.
   Guard protiv dvoklika je gađao nepostojeću kolonu (tabela ima `kreirano`),
   pa PostgREST odbija ceo upit. Advokat NIJE MOGAO da kreira klijenta —
   prvi korak celog poslovnog toka. Nijedan klijent nije nastao posle 2026-07-19.

2. `POST /api/intake/kreiraj` je vraćao `success: True` i `predmet_id` i kada
   veza klijent↔predmet nije upisana. `static/vindex.js::_intakeKreiraj` čita
   samo `d.predmet_id` — `klijent_povezan` ne čita niko. Mereno stanje baze:
   **`predmet_klijenti` 0 redova uz 19 predmeta i 5 klijenata.**

3. `GET /api/predmeti/{id}/workspace` → **HTTP 500 i sopstvenom vlasniku**.
   `UsageService.consume` → `_claim_cooldown_atomic` čita `.data` sa rezultata
   `maybe_single()`, a `postgrest 2.28.3` na 0 redova vraća `None`. Za novog
   korisnika red `feature_usage` ne postoji — dakle otvaranje predmeta je
   padalo svakom novom korisniku.

4. Provera vlasništva `.single()` je na tuđem redu dizala PostgREST grešku, pa
   su `GET /klijenti/{id}` i `/workspace` vraćali **500 umesto 404**, a grana
   `if not res.data: raise 404` bila je mrtav kod.

ZAŠTO OVI TESTOVI IZGLEDAJU OVAKO

Test koji pozove funkciju sa idealnim mockom ne bi uhvatio nijedan od ova četiri
kvara — sva četiri su nastala na spoju sa STVARNIM ponašanjem baze i biblioteke.
Zato lažni Supabase ovde **odbija nepostojeće kolone sa 42703**, tačno kao
PostgREST, a ugovor `maybe_single()` se meri na stvarnoj biblioteci.
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

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)

import pytest  # noqa: E402

UID = "11111111-1111-1111-1111-111111111111"
TUDJI_UID = "22222222-2222-2222-2222-222222222222"
KLIJENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PREDMET = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


# ═══════════════════════════════════════════════════════════════════════════
# LAŽNI POSTGREST — odbija nepostojeće kolone, kao prava baza
# ═══════════════════════════════════════════════════════════════════════════
#
# Kolone su prepisane iz PRODUKCIJSKE šeme (sonda `select(<kolona>)&limit=0`).
# Zato je ovo ugovor, ne pretpostavka: ako neko doda upit nad kolonom koje nema,
# test pada isto kao produkcija — umesto da mock ćutke prihvati sve.

SEMA = {
    "klijenti": {
        "id", "user_id", "tip", "ime", "prezime", "firma", "email", "telefon",
        "adresa", "napomena", "maticni_broj", "pravni_osnov_obrade", "status",
        "aktivan", "kreirano", "azurirano", "datum_nastanka", "deleted_at",
        "datum_poslednje_aktivnosti", "jmbg_encrypted", "broj_pasosa_encrypted",
        "pib_encrypted", "saglasnost_datum", "saglasnost_dokument_id",
        "connected_persons",
    },
    "predmeti": {
        "id", "user_id", "naziv", "opis", "tip", "status", "created_at",
        "updated_at", "broj_predmeta", "case_dna", "kanban_faza", "rizik",
        "tuzeni", "tuzilac", "vrednost_spora",
    },
    "predmet_klijenti": {"predmet_id", "klijent_id", "uloga_klijenta",
                         "napomena", "kreirano", "uloga"},
}


class NepostojecaKolona(Exception):
    """Ono što PostgREST vrati kao 42703 — odbija se CEO upit."""


class _Upit:
    def __init__(self, tabela, baza):
        self.t, self.baza = tabela, baza
        self.f, self.op, self.payload = {}, "select", None

    def _proveri(self, *kolone):
        dozvoljene = SEMA.get(self.t)
        if dozvoljene is None:
            return
        for k in kolone:
            k = (k or "").strip()
            if not k or k == "*" or "(" in k:
                continue
            if k not in dozvoljene:
                raise NepostojecaKolona(
                    f'column {self.t}.{k} does not exist')

    def select(self, sta="*", *a, **k):
        self.op = "select"
        self._proveri(*[c.strip() for c in str(sta).split(",")])
        return self

    def insert(self, row, *a, **k):
        self.op, self.payload = "insert", row
        self._proveri(*row.keys())
        return self

    def update(self, row, *a, **k):
        self.op, self.payload = "update", row
        self._proveri(*row.keys())
        return self

    def delete(self, *a, **k):
        self.op = "delete"
        return self

    def eq(self, kol, v):
        self._proveri(kol)
        self.f[kol] = v
        return self

    def neq(self, kol, v):
        self._proveri(kol)
        return self

    def gte(self, kol, v):
        self._proveri(kol)
        return self

    def is_(self, kol, v):
        self._proveri(kol)
        return self

    def in_(self, kol, v):
        self._proveri(kol)
        self.f[kol] = list(v)
        return self

    def order(self, kol=None, *a, **k):
        if kol:
            self._proveri(kol)
        return self

    def limit(self, *a, **k):
        return self

    def single(self):
        self._jedan = True
        return self

    def maybe_single(self):
        self._jedan = True
        return self

    def execute(self):
        self.baza.dnevnik.append((self.t, self.op, dict(self.f), self.payload))
        if self.op == "insert":
            if self.t == "predmet_klijenti":
                if self.baza.veza_puca:
                    raise RuntimeError("upis veze pao")
                self.baza.veze.append(dict(self.payload))
                return MagicMock(data=[dict(self.payload)])
            if self.t == "predmeti":
                self.baza.predmeti.append(PREDMET)
                return MagicMock(data=[{"id": PREDMET, "naziv": self.payload.get("naziv")}])
            return MagicMock(data=[{"id": "x"}])
        if self.op == "delete":
            if self.t == "predmeti":
                self.baza.predmeti = [p for p in self.baza.predmeti if p != self.f.get("id")]
            return MagicMock(data=[])
        if self.op == "update":
            return MagicMock(data=[])
        if self.t == "klijenti":
            if self.f.get("id") == KLIJENT and self.f.get("user_id") == UID:
                return MagicMock(data={"id": KLIJENT})
            # 0 redova -> ugovor iz shared/postgrest_compat.py
            return MagicMock(data=None)
        return MagicMock(data=[])


class _Baza:
    def __init__(self, veza_puca=False):
        self.veze, self.predmeti, self.dnevnik = [], [], []
        self.veza_puca = veza_puca

    def table(self, ime):
        return _Upit(ime, self)


# ═══════════════════════════════════════════════════════════════════════════
# 1 — UGOVOR `maybe_single()` (uzrok kvara #3 i #4)
# ═══════════════════════════════════════════════════════════════════════════

def test_1_maybe_single_nikad_ne_vraca_None():
    """Ovo je jedina tvrdnja koja stoji između 201 poziva i HTTP 500.

    Meri se STVARNA biblioteka, ne mock: `postgrest 2.28.3` na 0 redova vraća
    `None`, pa `.data` diže AttributeError. `shared/postgrest_compat.py` vraća
    ugovor na objekat sa `data=None`.
    """
    import shared.deps  # noqa: F401 — uvoz primenjuje šim
    from shared.postgrest_compat import je_primenjen
    assert je_primenjen(), "šim nije primenjen — 201 poziv .data ponovo pada u 500"

    from postgrest._sync.request_builder import SyncMaybeSingleRequestBuilder
    from postgrest.base_request_builder import APIResponse

    class _Zahtev:
        def send(self):
            o = MagicMock()
            o.is_success = True
            return o

    with patch.object(APIResponse, "from_http_request_response",
                      staticmethod(lambda r: APIResponse(data=[], count=None))):
        rez = SyncMaybeSingleRequestBuilder(_Zahtev()).execute()

    assert rez is not None, "0 redova je vratilo None — pozivalac pada na .data"
    assert rez.data is None


def test_1b_sim_je_idempotentan():
    from shared.postgrest_compat import primeni, je_primenjen
    assert je_primenjen()
    assert primeni() == 0, "dvostruka primena bi umotala šim u samog sebe"


# ═══════════════════════════════════════════════════════════════════════════
# 2 — KREIRANJE KLIJENTA NE SME DA GAĐA NEPOSTOJEĆU KOLONU (kvar #1)
# ═══════════════════════════════════════════════════════════════════════════

def _pozovi(ruta, *a, **k):
    f = ruta
    while hasattr(f, "__wrapped__"):
        f = f.__wrapped__
    return asyncio.run(f(*a, **k))


def test_2_create_klijent_koristi_postojece_kolone():
    """Ovaj test pada tačno na greški koja je oborila ceo tok: upit nad
    `klijenti.created_at`. Lažna baza odbija nepostojeću kolonu isto kao
    PostgREST, pa mock ne može da sakrije drift."""
    import klijenti.router as KR

    baza = _Baza()
    zahtev = MagicMock()
    zahtev.client = MagicMock(host="127.0.0.1")

    async def _auth(_r):
        return {"user_id": UID, "email": "a@b.c", "role": "advokat",
                "role_str": "advokat"}

    req = KR.KlijentCreateReq(ime="Testko", prezime="Testic", tip="fizicko")

    with patch.object(KR, "_auth_from_request", _auth), \
         patch.object(KR, "_get_supa", lambda: baza), \
         patch.object(KR, "get_client_ip", lambda r: "127.0.0.1"), \
         patch.object(KR, "log_event", lambda **kw: asyncio.sleep(0)):
        out = _pozovi(KR.create_klijent, req, zahtev)

    assert out.get("status") == "kreiran", out
    upiti = [(t, f) for t, op, f, _ in baza.dnevnik if t == "klijenti" and op == "select"]
    assert upiti, "dedup provera se uopšte nije izvršila"


def test_2b_lazna_baza_stvarno_odbija_nepostojecu_kolonu():
    """Kontrola nad samim merenjem: ako lažna baza ne odbija drift, test 2 ne
    dokazuje ništa."""
    b = _Baza()
    with pytest.raises(NepostojecaKolona):
        b.table("klijenti").select("id, created_at").execute()


# ═══════════════════════════════════════════════════════════════════════════
# 3 — VEZA KLIJENT↔PREDMET (kvar #2)
# ═══════════════════════════════════════════════════════════════════════════

def _vozi_intake(baza, klijent_id=KLIJENT):
    import routers.intake as IN

    body = IN.IntakeKreirajReq(klijent_id=klijent_id, naziv="NS001 predmet",
                               opis="x", tip="opsti", dokumenti=[])
    zahtev = MagicMock()
    zahtev.client = MagicMock(host="127.0.0.1")

    async def _nista(*a, **k):
        return None

    f = IN.intake_kreiraj
    while hasattr(f, "__wrapped__"):
        f = f.__wrapped__

    with patch.object(IN, "_get_supa", lambda: baza), \
         patch("shared.audit_immutable.log_action", _nista), \
         patch("services.case_pipeline.run_case_pipeline", _nista):
        return asyncio.run(f(body, zahtev, user={"user_id": UID, "email": "a@b.c"}))


def test_3_uspesan_tok_upisuje_vezu():
    baza = _Baza()
    out = _vozi_intake(baza)
    assert out["success"] is True
    assert out["klijent_povezan"] is True
    assert len(baza.veze) == 1, baza.veze
    assert baza.veze[0]["klijent_id"] == KLIJENT
    assert baza.predmeti == [PREDMET], "predmet je nestao iako je veza upisana"


def test_3b_pad_upisa_veze_NE_sme_da_vrati_uspeh():
    """NAJVAŽNIJI TEST FAZE 1.

    Ranije: `logger.warning`, `success: True`, `predmet_id` u odgovoru — advokat
    vidi kreiran predmet, baza nema vezu, i niko to nikad ne sazna.
    """
    from fastapi import HTTPException

    baza = _Baza(veza_puca=True)
    with pytest.raises(HTTPException) as e:
        _vozi_intake(baza)
    assert e.value.status_code == 500
    assert baza.veze == []
    assert baza.predmeti == [], "predmet bez klijenta je ostao u bazi"


def test_3c_tudji_klijent_ne_pravi_predmet():
    """Klijent koji nije korisnikov: 404, i NIJEDAN predmet ne sme da ostane."""
    from fastapi import HTTPException

    baza = _Baza()
    with pytest.raises(HTTPException) as e:
        _vozi_intake(baza, klijent_id="cccccccc-cccc-cccc-cccc-cccccccccccc")
    assert e.value.status_code == 404
    assert baza.veze == []
    assert baza.predmeti == []


def test_3d_odgovor_ne_moze_da_tvrdi_uspeh_bez_veze():
    """Brava nad OBLIKOM odgovora, nezavisno od implementacije.

    Kombinacija `success=True` + `klijent_povezan=False` je stanje koje UI ne
    ume da razlikuje od potpunog uspeha — zato ne sme da postoji.
    """
    baza = _Baza()
    out = _vozi_intake(baza)
    assert not (out.get("success") and out.get("klijent_povezan") is False)
