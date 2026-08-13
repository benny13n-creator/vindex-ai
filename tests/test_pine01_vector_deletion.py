# -*- coding: utf-8 -*-
"""
BETA-DATA-PINE-01 — DOKAZIV, AUTORIZOVAN, DETERMINISTIČKI I VERIFIKOVAN DELETE.

ŠTA JE BILO

Nije postojao nijedan način da se iz Pinecone-a ukloni tačno jedan dokument.
Najuži izvodljiv zahvat bio je `delete_all` nad namespace-om — što za
`kancelarija_{id}` znači **sve dokumente cele kancelarije**. GDPR čl. 17 je bio
tehnički nesprovodiv.

NAJVAŽNIJA ODLUKA U DIZAJNU

Ulaz je `document_id`, **nikad Pinecone vector ID iz zahteva**. Da funkcija
prima vector ID spolja, autorizacija bi bila zaobiđena po definiciji. ID-evi se
izvode iz reda u bazi koji je prošao kanonsku kapiju.

ZAŠTO LAŽNI PINECONE POŠTUJE PREFIKS I `delete`

Mandat §11 zabranjuje testove koji rekonstruišu implementaciju i `MagicMock` kao
dokaz autorizacije. `_LazniIndeks` ispod stvarno čuva vektore, stvarno filtrira
po prefiksu i stvarno ih briše — pa mutacija (uklonjena kapija) STVARNO obara
testove, umesto da mock vrati unapred zadatu vrednost.
"""
import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from shared.vector_deletion import (  # noqa: E402
    ORPHAN_UNIDENTIFIABLE,
    Ishod,
    klasifikuj_orphan,
    obrisi_vektore_dokumenta,
)
from shared.vector_identity import (  # noqa: E402
    canonical_vector_id,
    verzija_dokumenta,
)

VLASNIK = "uid-vlasnik"
NAPADAC = "uid-napadac"
DELEGAT = "uid-delegat"

PRED_A = "11111111-1111-1111-1111-111111111111"
PRED_B = "22222222-2222-2222-2222-222222222222"
NS = "kancelarija_firma-A"
NS_B = "kancelarija_firma-B"


# ═══════════════════════════════════════════════════════════════════════════
# LAŽNI PINECONE — pravi prefiks, pravo brisanje
# ═══════════════════════════════════════════════════════════════════════════

class _LazniIndeks:
    def __init__(self):
        self.prostor = {}          # ns -> set(id)
        self.delete_pozivi = []
        self.list_puca = False

    def dodaj(self, ns, idevi):
        self.prostor.setdefault(ns, set()).update(idevi)

    def list(self, prefix=None, namespace=None):
        if self.list_puca:
            raise RuntimeError("Pinecone nedostupan")
        pogodjeni = sorted(i for i in self.prostor.get(namespace, set())
                           if not prefix or i.startswith(prefix))
        # Pinecone `list` je generator strana.
        yield pogodjeni

    def delete(self, ids=None, namespace=None, delete_all=None, filter=None):
        self.delete_pozivi.append(
            {"ids": list(ids or []), "namespace": namespace,
             "delete_all": delete_all, "filter": filter})
        if delete_all:
            raise AssertionError("delete_all se NIKAD ne sme pozvati iz ovog puta")
        for i in (ids or []):
            self.prostor.get(namespace, set()).discard(i)

    def svi(self, ns):
        return sorted(self.prostor.get(ns, set()))


class _FakeSupa:
    def __init__(self, predmeti, dokumenti, delegacije=None):
        self._p, self._d, self._g = predmeti, dokumenti, delegacije or []

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

            def limit(self, n):
                return self

            def execute(self):
                izvor = {"predmeti": spolja._p, "predmet_dokumenti": spolja._d,
                         "predmet_delegiranja": spolja._g}.get(self.ime, [])
                d = [r for r in izvor
                     if all(r.get(k) == v for k, v in self.u.items())]
                return MagicMock(data=d)
        return _Q()


def _svet(n_chunks=3, tekst="Ugovor o zakupu"):
    """Dva predmeta dva vlasnika. Dokument u PRED_A ima `n_chunks` vektora,
    plus jedan brat-dokument i jedan dokument druge firme."""
    v = verzija_dokumenta(tekst)
    v_brat = verzija_dokumenta("Drugi dokument")
    v_b = verzija_dokumenta(tekst)          # ISTI sadržaj, druga firma

    ix = _LazniIndeks()
    ciljni = [canonical_vector_id(PRED_A, v, i) for i in range(n_chunks)]
    brat = [canonical_vector_id(PRED_A, v_brat, i) for i in range(2)]
    tudji = [canonical_vector_id(PRED_B, v_b, i) for i in range(2)]
    ix.dodaj(NS, ciljni + brat)
    ix.dodaj(NS_B, tudji)

    supa = _FakeSupa(
        predmeti=[{"id": PRED_A, "user_id": VLASNIK},
                  {"id": PRED_B, "user_id": NAPADAC}],
        dokumenti=[
            {"id": "dok-cilj", "predmet_id": PRED_A, "user_id": VLASNIK,
             "content_sha256": v, "pinecone_namespace": NS},
            {"id": "dok-brat", "predmet_id": PRED_A, "user_id": VLASNIK,
             "content_sha256": v_brat, "pinecone_namespace": NS},
            {"id": "dok-tudji", "predmet_id": PRED_B, "user_id": NAPADAC,
             "content_sha256": v_b, "pinecone_namespace": NS_B},
        ],
    )
    return supa, ix, ciljni, brat, tudji


def _obrisi(supa, ix, user_id=VLASNIK, predmet_id=PRED_A, document_id="dok-cilj"):
    return obrisi_vektore_dokumenta(supa, ix, user_id=user_id,
                                    predmet_id=predmet_id,
                                    document_id=document_id)


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4 — MULTICHUNK: TAČNO SVI, I NIŠTA VIŠE
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("n", [1, 10, 137])
def test_pine01_brise_TACNO_sve_chunkove_dokumenta(n):
    """§4: 1, 10, 100+ chunk-ova. Provera BEFORE → DELETE → AFTER."""
    supa, ix, ciljni, brat, tudji = _svet(n_chunks=n)
    assert len(ix.svi(NS)) == n + 2                      # BEFORE

    r = _obrisi(supa, ix)

    assert r.ishod == Ishod.DELETED, r
    assert r.obrisano == n
    assert not [i for i in ix.svi(NS) if i in ciljni], "ostao chunk cilja"
    assert sorted(ix.svi(NS)) == sorted(brat), "brat-dokument je oštećen"
    assert ix.svi(NS_B) == sorted(tudji), "dokument druge firme je oštećen"


def test_pine01_chunk_index_10_ne_brise_chunk_1():
    """Zamka prefiksa: `_c1` je tekstualni prefiks od `_c10`. Ovde se briše ceo
    dokument, pa moraju otići svi — ali provera postoji da se ne bi oslonili na
    slučajnost."""
    supa, ix, ciljni, _, _ = _svet(n_chunks=12)
    r = _obrisi(supa, ix)
    assert r.obrisano == 12
    assert all(i not in ix.svi(NS) for i in ciljni)


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3 — CROSS-TENANT / CROSS-PREDMET
# ═══════════════════════════════════════════════════════════════════════════

def test_pine01_napadac_ne_moze_obrisati_tudji_dokument():
    """NAJVAŽNIJI BEZBEDNOSNI TEST U FAJLU."""
    supa, ix, ciljni, _, _ = _svet()
    pre = ix.svi(NS)
    r = obrisi_vektore_dokumenta(supa, ix, user_id=NAPADAC,
                                 predmet_id=PRED_A, document_id="dok-cilj")
    assert r.ishod == Ishod.REFUSED
    assert ix.svi(NS) == pre, "vektori su dirnuti uprkos odbijanju"
    assert ix.delete_pozivi == [], "delete je uopšte pozvan"


def test_pine01_tudji_predmet_id_uz_svoj_dokument_je_odbijen():
    """Napadač prosleđuje SVOJ predmet, a tuđi document_id."""
    supa, ix, _, _, _ = _svet()
    r = obrisi_vektore_dokumenta(supa, ix, user_id=NAPADAC,
                                 predmet_id=PRED_B, document_id="dok-cilj")
    assert r.ishod == Ishod.REFUSED
    assert ix.delete_pozivi == []


def test_pine01_isti_sadrzaj_druge_firme_ostaje_netaknut():
    """Dva korisnika otpremila DOSLOVNO isti fajl — heš identičan. `scope` u
    ID-u je jedino što ih razdvaja."""
    supa, ix, _, _, tudji = _svet()
    r = _obrisi(supa, ix)
    assert r.ishod == Ishod.DELETED
    assert ix.svi(NS_B) == sorted(tudji)


def test_pine01_delegat_sme_ali_samo_kroz_aktivnu_delegaciju():
    supa, ix, ciljni, _, _ = _svet()
    r = obrisi_vektore_dokumenta(supa, ix, user_id=DELEGAT,
                                 predmet_id=PRED_A, document_id="dok-cilj")
    assert r.ishod == Ishod.REFUSED

    supa._g = [{"id": "d1", "predmet_id": PRED_A, "na_user_id": DELEGAT,
                "status": "aktivno"}]
    r2 = obrisi_vektore_dokumenta(supa, ix, user_id=DELEGAT,
                                  predmet_id=PRED_A, document_id="dok-cilj")
    assert r2.ishod == Ishod.DELETED


def test_pine01_opozvana_delegacija_ne_daje_pravo_brisanja():
    supa, ix, _, _, _ = _svet()
    supa._g = [{"id": "d1", "predmet_id": PRED_A, "na_user_id": DELEGAT,
                "status": "opozvano"}]
    r = obrisi_vektore_dokumenta(supa, ix, user_id=DELEGAT,
                                 predmet_id=PRED_A, document_id="dok-cilj")
    assert r.ishod == Ishod.REFUSED


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 5 — IDEMPOTENTNOST
# ═══════════════════════════════════════════════════════════════════════════

def test_pine01_ponovljeno_brisanje_je_idempotentno_i_ne_siri_obim():
    """§5: „0 preostalih" nije dovoljan dokaz — mora se proveriti da drugi
    poziv nije zahvatio širi opseg."""
    supa, ix, _, brat, tudji = _svet()
    assert _obrisi(supa, ix).ishod == Ishod.DELETED

    r2 = _obrisi(supa, ix)
    assert r2.ishod == Ishod.ALREADY_ABSENT
    assert sorted(ix.svi(NS)) == sorted(brat), "drugi delete je proširio obim"
    assert ix.svi(NS_B) == sorted(tudji)
    assert all(not p["delete_all"] for p in ix.delete_pozivi)


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 10 — NIKAD LAŽAN USPEH
# ═══════════════════════════════════════════════════════════════════════════

def test_pine01_nekanonski_identitet_se_odbija_a_ne_pogadja():
    """Legacy dokument sa 64-znakovnim hešem bajtova. Ne sme se obrisati po
    pretpostavci da mu je identitet kanonski."""
    supa, ix, _, _, _ = _svet()
    supa._d[0]["content_sha256"] = "a" * 64
    r = _obrisi(supa, ix)
    assert r.ishod == Ishod.REFUSED
    assert "kanonski" in r.razlog.lower()
    assert ix.delete_pozivi == []


@pytest.mark.parametrize("polje", ["content_sha256", "pinecone_namespace"])
def test_pine01_bez_identiteta_nema_brisanja(polje):
    supa, ix, _, _, _ = _svet()
    supa._d[0][polje] = ""
    r = _obrisi(supa, ix)
    assert r.ishod == Ishod.REFUSED
    assert ix.delete_pozivi == []


def test_pine01_neuspelo_listanje_je_odbijanje_a_ne_uspeh():
    """„Ne znam šta je tamo" nikad ne sme da postane „nema ničega"."""
    supa, ix, _, _, _ = _svet()
    ix.list_puca = True
    r = _obrisi(supa, ix)
    assert r.ishod == Ishod.REFUSED
    assert ix.delete_pozivi == []


def test_pine01_neuspela_verifikacija_nije_uspeh():
    """§8: HTTP 200 nije dokaz. Ako posle brisanja vektori i dalje stoje,
    ishod je PARTIAL_FAILURE."""
    supa, ix, _, _, _ = _svet()
    ix.delete = lambda **kw: ix.delete_pozivi.append(kw)   # ne briše ništa
    r = _obrisi(supa, ix)
    assert r.ishod == Ishod.PARTIAL_FAILURE
    assert r.obrisano < r.ocekivano


def test_pine01_delete_all_se_nikad_ne_poziva():
    """`delete_all` bi obrisao sve dokumente cele kancelarije."""
    supa, ix, _, _, _ = _svet()
    _obrisi(supa, ix)
    assert ix.delete_pozivi
    for p in ix.delete_pozivi:
        assert not p["delete_all"]
        assert p["filter"] is None
        assert p["ids"], "brisanje bez izričite liste ID-eva"


def test_pine01_nepostojeci_dokument_je_REFUSED_a_ne_izuzetak():
    supa, ix, _, _, _ = _svet()
    r = _obrisi(supa, ix, document_id="ne-postoji")
    assert r.ishod == Ishod.REFUSED
    assert ix.delete_pozivi == []


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1 — KARANTIN
# ═══════════════════════════════════════════════════════════════════════════

def test_pine01_uuid4_vektor_je_ORPHAN_UNIDENTIFIABLE():
    """30 postojećih klijentskih vektora ima `uuid4` ID i nijedno `vx_*` polje.
    Karantin je KONAČNA klasifikacija, ne međukorak ka brisanju."""
    assert klasifikuj_orphan("3f2b1c9e4a5d6f708192a3b4c5d6e7f8", {}) == \
        ORPHAN_UNIDENTIFIABLE
    assert klasifikuj_orphan("3f2b1c9e4a5d6f708192a3b4c5d6e7f8",
                             {"session_id": "x", "source_filename": "a.pdf"}) == \
        ORPHAN_UNIDENTIFIABLE


def test_pine01_kanonski_i_legacy_se_ne_mesaju_sa_orphanom():
    v = verzija_dokumenta("t")
    assert klasifikuj_orphan(canonical_vector_id(PRED_A, v, 0)) != \
        ORPHAN_UNIDENTIFIABLE
    assert klasifikuj_orphan("Rev-123-2019__chunk_4") != ORPHAN_UNIDENTIFIABLE
    assert klasifikuj_orphan("kb_uid_42") != ORPHAN_UNIDENTIFIABLE


# ═══════════════════════════════════════════════════════════════════════════
# KONTROLA NAD TEST ALATOM
# ═══════════════════════════════════════════════════════════════════════════

def test_lazni_indeks_stvarno_filtrira_i_brise():
    """Bez ovoga ostalim testovima nema dokazne vrednosti."""
    ix = _LazniIndeks()
    ix.dodaj("n", ["a_c0", "a_c1", "b_c0"])
    assert list(ix.list(prefix="a_", namespace="n"))[0] == ["a_c0", "a_c1"]
    ix.delete(ids=["a_c0"], namespace="n")
    assert ix.svi("n") == ["a_c1", "b_c0"]


# ═══════════════════════════════════════════════════════════════════════════
# PROVAJDER KOJI SE LOŠE PONAŠA — mutacija G je otkrila rupu u testovima
# ═══════════════════════════════════════════════════════════════════════════
#
# Mutacija „ukloni proveru prefiksa" prvo nije oborila nijedan test, jer lažni
# indeks uvek filtrira ispravno — pa provera nikad nije došla na red. §6 nalaže
# da se to istraži, ne da se mutacija proglasi bezopasnom.
#
# Provera postoji baš za slučaj da provajder vrati nešto van prefiksa: greška u
# Pinecone-u, budući `list` sa drugačijom semantikom, ili prefiks koji se
# slučajno poklopi. Tada se NE SME obrisati ništa — bolje odbiti nego obrisati
# tuđe.

class _NepouzdanIndeks(_LazniIndeks):
    """Vraća i jedan ID koji NE pripada traženom prefiksu."""

    def __init__(self, podmetnuti):
        super().__init__()
        self._podmetnuti = podmetnuti

    def list(self, prefix=None, namespace=None):
        pravi = sorted(i for i in self.prostor.get(namespace, set())
                       if not prefix or i.startswith(prefix))
        yield pravi + [self._podmetnuti]


def test_pine01_id_van_prefiksa_obara_celo_brisanje():
    """Ako listanje vrati ijedan ID van kanonskog prefiksa, NIŠTA se ne briše."""
    supa, _, ciljni, brat, _ = _svet()
    ix = _NepouzdanIndeks(podmetnuti=brat[0])
    ix.dodaj(NS, ciljni + brat)

    r = _obrisi(supa, ix)

    assert r.ishod == Ishod.REFUSED
    assert "prefiks" in r.razlog.lower()
    assert ix.delete_pozivi == [], "brisanje je pozvano uprkos stranom ID-u"
    assert sorted(ix.svi(NS)) == sorted(ciljni + brat), "podaci su dirnuti"


def test_pine01_podmetnut_id_druge_firme_ne_moze_biti_obrisan():
    """Najgori oblik iste greške: provajder vrati ID iz TUĐEG namespace-a."""
    supa, _, ciljni, brat, tudji = _svet()
    ix = _NepouzdanIndeks(podmetnuti=tudji[0])
    ix.dodaj(NS, ciljni + brat)
    ix.dodaj(NS_B, tudji)

    r = _obrisi(supa, ix)

    assert r.ishod == Ishod.REFUSED
    assert ix.svi(NS_B) == sorted(tudji), "vektor druge firme je obrisan"
