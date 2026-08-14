# -*- coding: utf-8 -*-
"""
BETA-P1-COLUMN-DRIFT-007 / DRIFT-001 — SLOJ „KLIJENTI" U PROVERI SUKOBA INTERESA
NIKAD NIJE IZVRŠEN.

ŠTA JE MERENO (samo čitanje produkcije, 2026-08-14)

`routers/conflict_check.py:207` bira `pib` sa tabele `klijenti`. Ta kolona ne
postoji — PIB se čuva šifrovan, kao `pib_encrypted`:

    ?select=id,ime,prezime,firma,email,pib  → 400 / 42703
                                               „column klijenti.pib does not exist"
    ?select=id,ime,prezime,firma,email      → 200

PostgREST odbija **ceo** zahtev, ne pojedinačno polje. Sloj 2 zato puca na
SVAKOM pozivu, a `except` ga upisuje kao `sloj_status["klijenti"] = "greška"`.

TRI POSLEDICE, SVE STALNE

  1. Pretraga po tabeli `klijenti` (ime · prezime · firma · email, pa preko
     `predmet_klijenti` do uloge u predmetu) **nikad se nije izvršila**. Sukob
     sa nekim ko je zaveden kao KLIJENT, a ne kao tužilac/tuženi u `predmeti`,
     ne može biti pronađen.
  2. `provera_potpuna` je uvek `False`, pa svaka provera prikazuje
     „⚠️ PROVERA NIJE POTPUNA". Jedini ekran čija je svrha da upozori vikao je
     isto svaki put — a upozorenje koje se uvek pali prestaje da bude
     upozorenje.
  3. `conflict_check` se nikad nije naplatio (`if _provera_potpuna: consume`).

ZAŠTO POSTOJEĆI TESTOVI OVO NISU UHVATILI

`tests/test_beta_p0_conflict_of_interest.py::_Supa.select()` prima **bilo koje**
ime kolone i vraća pripremljene redove. Test i implementacija su bili na istoj
strani ugovora: nijedan od njih ne zna šta baza stvarno ima. Zato lažni Supabase
ovde odbija nepostojeće kolone isto kao PostgREST.

ZAŠTO SE PIB NE POPRAVLJA „PREIMENOVANJEM U pib_encrypted"

Poređenje otvorenog PIB-a iz forme sa šifrovanom vrednošću ne bi se nikad
poklopilo — dobili bismo tih lažno-negativan nalaz umesto glasne greške. A
dešifrovanje svih klijenata na svakoj proveri bi zaobišlo kontrolu iz
BETA-P0-SENSITIVE-DATA-AUDIT (dešifrovanje JMBG/PIB zahteva strog audit trag).

Zato: sloj radi nad poljima koja se STVARNO mogu pretražiti, a zahtev koji
traži podudaranje po PIB-u degradira proveru na nepotpunu — nikad se tiho ne
ignoriše.
"""
import asyncio
import io
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)

import pytest  # noqa: E402

import routers.conflict_check as cc  # noqa: E402

UID = "uid-advokat"

# Izmerene produkcione kolone (PostgREST OpenAPI koren, 2026-08-14).
SEMA = {
    "klijenti": {"adresa", "aktivan", "azurirano", "broj_pasosa_encrypted",
                 "connected_persons", "datum_nastanka",
                 "datum_poslednje_aktivnosti", "deleted_at", "email", "firma",
                 "id", "ime", "jmbg_encrypted", "kreirano", "maticni_broj",
                 "napomena", "pib_encrypted", "pravni_osnov_obrade", "prezime",
                 "saglasnost_datum", "saglasnost_dokument_id", "status",
                 "telefon", "tip", "user_id"},
    "predmeti": {"broj_predmeta", "case_dna", "created_at", "id", "kanban_faza",
                 "naziv", "opis", "rizik", "status", "tip", "tuzeni", "tuzilac",
                 "updated_at", "user_id", "vrednost_spora"},
    "predmet_klijenti": {"id", "klijent_id", "predmet_id", "uloga",
                         "created_at", "uloga_klijenta"},
    "predmet_hronologija": {"akter", "created_at", "datum", "datum_iso",
                            "dogadjaj", "dokument_naziv", "id", "predmet_id",
                            "user_id", "vaznost"},
}


class _Supa:
    """Lažni Supabase koji odbija nepostojeće kolone TAČNO kao PostgREST:
    ceo zahtev pada, ne samo nepoznato polje."""

    def __init__(self, redovi=None):
        self.redovi = redovi or {}
        self.trazene_kolone = {}
        self.izvrseni_upiti = []

    def table(self, ime):
        spolja = self

        class _Q:
            def __init__(self):
                self.ime, self.filtri = ime, {}

            def select(self, izraz, *a, **k):
                # Ugnježdeni resurs `predmeti(naziv,status,tip)` pripada SVOJOJ
                # tabeli — isto kao kod PostgREST-a.
                spolja_kolone, dubina, bafer, ugnj = set(), 0, "", ""
                for c in izraz:
                    if c == "(":
                        dubina += 1
                        ugnj = bafer.strip()
                        bafer = ""
                    elif c == ")":
                        dubina -= 1
                        bafer = ""
                    elif c == ",":
                        if dubina == 0 and bafer.strip():
                            spolja_kolone.add(bafer.strip())
                        bafer = ""
                    else:
                        bafer += c
                if bafer.strip() and dubina == 0:
                    spolja_kolone.add(bafer.strip())
                spolja.trazene_kolone.setdefault(ime, set()).update(spolja_kolone)
                nepoznate = spolja_kolone - SEMA.get(ime, spolja_kolone)
                if nepoznate:
                    raise RuntimeError(
                        "column %s.%s does not exist (42703)"
                        % (ime, sorted(nepoznate)[0]))
                return self

            def eq(self, k, v):
                self.filtri[k] = v
                return self

            def in_(self, k, v):
                self.filtri["_in"] = list(v)
                return self

            def neq(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            def order(self, *a, **k):
                return self

            def execute(self):
                spolja.izvrseni_upiti.append(self.ime)
                return MagicMock(data=spolja.redovi.get(self.ime, []))
        return _Q()


KLIJENT = {"id": "k1", "ime": "Petar", "prezime": "Petrović",
           "firma": "Beograd Gradnja d.o.o.", "email": "petar@bg.rs"}

VEZA = {"klijent_id": "k1", "predmet_id": "p9", "uloga": "protivna strana",
        "predmeti": {"naziv": "Spor o naknadi", "status": "aktivan",
                     "tip": "parnicni"}}


def _pozovi(supa, **kw):
    req = cc.ConflictReq(**({"ime_prezime": "Petar Petrović"} | kw))

    async def _consume(*a, **k):
        return None

    with patch.object(cc, "_get_supa", return_value=supa), \
         patch.object(cc.UsageService, "consume", new=_consume):
        return asyncio.run(cc.check_conflict(req, {"user_id": UID, "email": "a@a.rs"}))


# ═══════════════════════════════════════════════════════════════════════════
# 1. SRŽ — SLOJ „KLIJENTI" MORA DA SE IZVRŠI
# ═══════════════════════════════════════════════════════════════════════════

def test_sloj_klijenti_se_STVARNO_izvrsava():
    """NAJVAŽNIJI TEST U FAJLU.

    Pre popravke je `select(... ,pib)` obarao ceo sloj na 42703, pa je
    `provera_potpuna` bila `False` na svakom pozivu, a pretraga po klijentima
    se nikad nije desila.
    """
    supa = _Supa(redovi={"predmeti": [], "klijenti": [KLIJENT],
                         "predmet_klijenti": [VEZA]})
    r = _pozovi(supa)
    assert "klijenti" not in r["slojevi_greska"], (
        "sloj klijenti i dalje puca: %s" % r["slojevi_greska"])
    assert r["provera_potpuna"] is True
    assert "klijenti" in supa.izvrseni_upiti


def test_sukob_preko_KLIJENATA_se_pronalazi():
    """Sukob koji postoji SAMO kroz tabelu klijenata — osoba nije upisana kao
    tužilac/tuženi ni u jednom predmetu. Taj put je bio potpuno mrtav."""
    supa = _Supa(redovi={"predmeti": [], "klijenti": [KLIJENT],
                         "predmet_klijenti": [VEZA]})
    r = _pozovi(supa)
    assert r["status"] == "conflict", r["poruka"]
    assert any(k["sloj"] == "klijenti" for k in r["konflikti"])
    assert r["ukupno"] >= 1


def test_nijedna_trazena_kolona_ne_izlazi_iz_izmerene_seme():
    """Brava nad IZVOROM kvara. Da je ovaj test postojao, `pib` nikad ne bi
    otišao u produkciju."""
    supa = _Supa(redovi={"predmeti": [], "klijenti": [KLIJENT],
                         "predmet_klijenti": [VEZA]})
    _pozovi(supa, advokat_ime="Mika Mikić")
    for tabela, kolone in supa.trazene_kolone.items():
        visak = kolone - SEMA[tabela]
        assert not visak, f"provera sukoba traži {tabela}.{sorted(visak)} — ne postoji"


def test_cista_provera_je_potpuna_i_zelena():
    """Kad nema pogodaka a svi slojevi rade, odgovor sme biti `clear` — i to je
    jedini slučaj u kom sme."""
    supa = _Supa(redovi={"predmeti": [], "klijenti": [], "predmet_klijenti": []})
    r = _pozovi(supa)
    assert r["status"] == "clear"
    assert r["provera_potpuna"] is True
    assert r["slojevi_greska"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. FAIL-CLOSED SE NE SME OSLABITI
# ═══════════════════════════════════════════════════════════════════════════

def test_pad_sloja_i_dalje_daje_NEPOTPUNU_proveru():
    """SOA2-006 mora da preživi ovu popravku: ako sloj stvarno padne, odgovor
    nikad ne sme biti `clear`."""
    class _Puca(_Supa):
        def table(self, ime):
            q = super().table(ime)
            if ime == "klijenti":
                q.execute = lambda: (_ for _ in ()).throw(RuntimeError("baza pala"))
            return q
    r = _pozovi(_Puca(redovi={"predmeti": [], "predmet_klijenti": []}))
    assert r["provera_potpuna"] is False
    assert r["status"] == "review"
    assert "klijenti" in r["slojevi_greska"]
    assert "NIJE POTPUNA" in r["poruka"].upper()


def test_pretraga_po_PIB_u_ne_sme_da_se_tiho_ignorise():
    """PIB je u bazi ŠIFROVAN i ne može se porediti jednakošću. Zahtev koji
    traži podudaranje po PIB-u zato mora degradirati proveru na nepotpunu —
    tiho ignorisanje bi bio lažno-negativan nalaz na etičkom ekranu."""
    supa = _Supa(redovi={"predmeti": [], "klijenti": [KLIJENT],
                         "predmet_klijenti": []})
    r = _pozovi(supa, pib="100200300")
    assert r["provera_potpuna"] is False, (
        "provera po PIB-u je prećutana kao da je izvršena"
    )
    assert r["status"] != "clear"


def test_bez_pib_a_provera_ostaje_potpuna():
    """Negativna kontrola: degradacija sme da se okine SAMO na PIB, inače bi
    popravka uvela trajno lažno „nepotpuno"."""
    supa = _Supa(redovi={"predmeti": [], "klijenti": [KLIJENT],
                         "predmet_klijenti": []})
    assert _pozovi(supa, email="petar@bg.rs")["provera_potpuna"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 3. POVERLJIVOST — POPRAVKA NE SME DA PROŠIRI PRISTUP
# ═══════════════════════════════════════════════════════════════════════════

def test_sifrovana_polja_se_ne_citaju():
    """Popravka ne sme da povuče `pib_encrypted` ni bilo koje drugo šifrovano
    polje — dešifrovanje zahteva strog audit (BETA-P0-SENSITIVE-DATA-AUDIT)."""
    supa = _Supa(redovi={"predmeti": [], "klijenti": [KLIJENT],
                         "predmet_klijenti": []})
    _pozovi(supa, pib="100200300")
    trazeno = supa.trazene_kolone.get("klijenti", set())
    for polje in ("pib_encrypted", "jmbg_encrypted", "broj_pasosa_encrypted"):
        assert polje not in trazeno, f"provera sukoba čita šifrovano polje {polje}"


def test_upit_ostaje_vezan_za_vlasnika():
    """Izolacija kancelarija ne sme da regresira."""
    izvor = io.open(os.path.join(_KOREN, "routers", "conflict_check.py"),
                    encoding="utf-8").read()
    isecak = izvor[izvor.index("SLOJ 2"):izvor.index("SLOJ 3")]
    assert '.eq("user_id", uid)' in isecak, (
        "sloj klijenti više nije ograničen na predmete prijavljenog advokata"
    )


def test_odgovor_ne_nosi_licne_podatke_klijenta():
    """U odgovor sme ime/firma koje je advokat sam uneo u proveru — nikad
    email, telefon ni šifrovana polja."""
    supa = _Supa(redovi={"predmeti": [], "klijenti": [KLIJENT],
                         "predmet_klijenti": [VEZA]})
    spojeno = str(_pozovi(supa))
    assert "petar@bg.rs" not in spojeno
