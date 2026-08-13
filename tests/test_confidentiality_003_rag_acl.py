# -*- coding: utf-8 -*-
"""
BETA-DATA-CONFIDENTIALITY-003 / F-01 — RAG JE ZAOBILAZIO ACL PREDMETA.

ŠTA JE BILO

`app/services/retrieve.py` je pretraživao `kancelarija_{id}` namespace sa
filterom samo po `type`:

    {"type": {"$in": ["case_doc", "draft_final"]}}

Dakle SVE trajne dokumente cele kancelarije, za svakog aktivnog člana. A
kanonska kapija za čitanje predmeta (`api.py::get_predmet`) propušta po tačno
dva osnova: vlasnik (`predmeti.user_id`) i aktivna delegacija
(`predmet_delegiranja`). **Članstvo u istoj kancelariji nije osnov.**

Posledica: član koji predmet ne može ni da otvori kroz API dobijao je doslovan
tekst iz njegovih dokumenata kroz RAG kontekst.

ZAŠTO NIJE BILO ZABORAVLJENO NEGO NEDOVRŠENO

`shared/kancelarija_utils.py:44` u sopstvenom docstringu kaže da `predmet_id`
stoji u metapodacima vektora „za scoping unutar tog namespace-a". Mehanizam je
ugrađen po dizajnu; filter koji bi ga koristio nikad nije napisan.

ZAŠTO OVAJ FAJL NE KORISTI MagicMock ZA AUTORIZACIJU

Postojeći `tests/test_institutional_rag_upgrade.py` gradi `mock_index` čiji
`query()` **ignoriše `filter`** i uvek vraća iste rezultate. Takav test prolazi
i sa kapijom i bez nje — pa ne dokazuje nijedno bezbednosno svojstvo. Mandat
§6 to izričito zabranjuje.

`_LazniIndeks` ispod je mali motor koji stvarno primenjuje Pinecone `$in`
semantiku nad metapodacima. Zato mutacija (uklonjena kapija) STVARNO obara
testove — i zato ovi testovi nešto znače.
"""
import os
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from shared.rag_acl import (  # noqa: E402
    dozvoljeni_predmeti,
    filter_za_namespace_vlasnika,
)

# ── Sentinel sadržaj: mora biti nezamenljiv, da se ne može slučajno poklopiti ──
TAJNA_A = "SECRET_A_DOCUMENT_001"
TAJNA_B = "SECRET_B_DOCUMENT_001"
TAJNA_T2 = "SECRET_TENANT_B_001"

NS_A = "kancelarija_firma-A"
NS_B = "kancelarija_firma-B"


# ═══════════════════════════════════════════════════════════════════════════
# LAŽNI PINECONE KOJI STVARNO POŠTUJE FILTERE
# ═══════════════════════════════════════════════════════════════════════════

class _LazniIndeks:
    """Implementira podskup Pinecone `filter` semantike koji ovaj kod koristi:
    `{"polje": {"$in": [...]}}` i doslovnu jednakost. Sve ostalo diže grešku,
    da test nikad ne bi tiho prošao nad filterom koji ne razume."""

    def __init__(self, vektori):
        self.vektori = vektori           # [(namespace, metadata, score)]
        self.videni_filteri = []         # forenzika: šta je kod stvarno poslao

    @staticmethod
    def _odgovara(meta, filter_):
        for polje, uslov in (filter_ or {}).items():
            vrednost = meta.get(polje)
            if isinstance(uslov, dict):
                if "$in" in uslov:
                    if vrednost not in uslov["$in"]:
                        return False
                else:
                    raise AssertionError(f"nepodržan operator u filteru: {uslov}")
            elif vrednost != uslov:
                return False
        return True

    def query(self, **kw):
        ns = kw.get("namespace", "")
        filter_ = kw.get("filter")
        self.videni_filteri.append((ns, filter_))
        matches = []
        for v_ns, meta, score in self.vektori:
            if v_ns != ns:
                continue
            if not self._odgovara(meta, filter_):
                continue
            m = MagicMock()
            m.metadata = meta
            m.score = score
            matches.append(m)
        rez = MagicMock()
        rez.matches = matches
        return rez


def _svet_vektora():
    """Jedna kancelarija (firma-A) sa DVA predmeta različitih vlasnika, plus
    druga kancelarija. Tačno scenario iz mandata §2."""
    return [
        (NS_A, {"predmet_id": "pred-A", "type": "case_doc", "chunk_index": 0,
                "article_label": "", "text": f"Ugovor. {TAJNA_A}"}, 0.90),
        (NS_A, {"predmet_id": "pred-B", "type": "case_doc", "chunk_index": 0,
                "article_label": "", "text": f"Presuda. {TAJNA_B}"}, 0.95),
        (NS_B, {"predmet_id": "pred-T2", "type": "case_doc", "chunk_index": 0,
                "article_label": "", "text": f"Tudja firma. {TAJNA_T2}"}, 0.99),
    ]


@contextmanager
def _stub_llm():
    """retrieve_documents bezuslovno zove nekoliko gpt-4o-mini poziva koji nemaju
    veze sa Pinecone-om. Bez ovoga bi test slao stvarne, naplative zahteve."""
    poruka = MagicMock()
    poruka.content = ""
    izbor = MagicMock()
    izbor.message = poruka
    odgovor = MagicMock()
    odgovor.choices = [izbor]
    klijent = MagicMock()
    klijent.chat.completions.create.return_value = odgovor
    with patch("app.services.retrieve._get_client", return_value=klijent):
        yield


def _pretrazi(dozvoljeni, namespace=NS_A, indeks=None):
    from app.services.retrieve import retrieve_documents
    indeks = indeks or _LazniIndeks(_svet_vektora())
    ugradnje = MagicMock()
    ugradnje.embed_query.return_value = [0.0] * 3072
    cohere = MagicMock()
    cohere.rerank.side_effect = Exception("bez cohere")
    with _stub_llm(), \
         patch("app.services.retrieve._get_index", return_value=indeks), \
         patch("app.services.retrieve._get_embeddings", return_value=ugradnje), \
         patch("app.services.retrieve._get_cohere", return_value=cohere):
        docs, meta = retrieve_documents(
            "Da li postoji klauzula o raskidu?",
            kancelarija_namespace=namespace,
            current_predmet_id="pred-A",
            dozvoljeni_predmeti=dozvoljeni,
        )
    return docs, meta, indeks


# ═══════════════════════════════════════════════════════════════════════════
# 1. SRŽ — TUĐI PREDMET ISTE KANCELARIJE NE SME DA SE POJAVI
# ═══════════════════════════════════════════════════════════════════════════

def test_f01_tudji_predmet_iste_kancelarije_nikad_ne_curi():
    """NAJVAŽNIJI TEST U FAJLU.

    Mandat §2: SECRET_A SME da se pojavi, SECRET_B NE SME NIKADA — iako su u
    ISTOJ kancelariji i istom namespace-u. Meri se stvarni vraćeni kontekst,
    ne HTTP status.
    """
    docs, meta, _ = _pretrazi(dozvoljeni=["pred-A"])
    spojeno = "\n".join(docs) + "\n" + str(meta.get("doc_passages", ""))
    assert TAJNA_B not in spojeno, (
        "TEKST TUĐEG PREDMETA JE PROCURIO KROZ RAG — F-01 nije zatvoren"
    )


def test_f01_sopstveni_predmet_i_dalje_stize():
    """Kapija ne sme da ubije funkciju. Institutional Learning ostaje —
    menja se samo SKUP predmeta, ne postojanje pretrage."""
    docs, meta, _ = _pretrazi(dozvoljeni=["pred-A"])
    spojeno = "\n".join(docs) + "\n" + str(meta.get("doc_passages", ""))
    assert TAJNA_A in spojeno, "sopstveni dokument mora i dalje da se nađe"


def test_f01_delegirani_predmet_se_pojavljuje_kad_je_autorizovan():
    """Pretraga preko više predmeta je stvarna funkcija proizvoda i ostaje —
    kad je pozivalac za oba predmeta autorizovan, oba smeju da se pojave."""
    docs, meta, _ = _pretrazi(dozvoljeni=["pred-A", "pred-B"])
    spojeno = "\n".join(docs) + "\n" + str(meta.get("doc_passages", ""))
    assert TAJNA_A in spojeno
    assert TAJNA_B in spojeno, "autorizovan drugi predmet mora da se pojavi"


def test_f01_filter_stvarno_stize_do_pineconea():
    """Dokaz da kapija nije ukras: ID predmeta mora biti U SAMOM UPITU ka
    provajderu, a ne primenjen naknadno nad već dovučenim rezultatima.
    Naknadno filtriranje bi značilo da je tekst već napustio Pinecone."""
    _, _, indeks = _pretrazi(dozvoljeni=["pred-A"])
    kanc = [f for ns, f in indeks.videni_filteri if ns == NS_A]
    assert kanc, "namespace kancelarije uopšte nije pretražen"
    assert any(f and "predmet_id" in f for f in kanc), (
        f"filter poslat Pinecone-u nema predmet_id: {kanc}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. CROSS-TENANT
# ═══════════════════════════════════════════════════════════════════════════

def test_f01_druga_kancelarija_nikad_ne_curi():
    docs, meta, _ = _pretrazi(dozvoljeni=["pred-A", "pred-B"], namespace=NS_A)
    spojeno = "\n".join(docs) + "\n" + str(meta.get("doc_passages", ""))
    assert TAJNA_T2 not in spojeno


def test_f01_cak_i_ako_je_tudji_predmet_u_dozvoljenima_namespace_stiti():
    """Dvostruka brana: i da autorizacija pogreši, namespace druge kancelarije
    se ne pretražuje jer ime namespace-a nikad ne dolazi od korisnika."""
    docs, meta, _ = _pretrazi(dozvoljeni=["pred-T2"], namespace=NS_A)
    spojeno = "\n".join(docs) + "\n" + str(meta.get("doc_passages", ""))
    assert TAJNA_T2 not in spojeno


# ═══════════════════════════════════════════════════════════════════════════
# 3. FAIL-CLOSED
# ═══════════════════════════════════════════════════════════════════════════

def test_f01_bez_izracunate_autorizacije_namespace_se_ne_dira():
    """`None` znači 'nije izračunato' i MORA da znači 'ne pretražuj'.

    Ovo je brava nad budućim pozivaocem: neko ko sutra doda novi poziv i
    zaboravi da prosledi listu ne otvara rupu — dobija prazan rezultat.
    """
    docs, meta, indeks = _pretrazi(dozvoljeni=None)
    spojeno = "\n".join(docs) + "\n" + str(meta.get("doc_passages", ""))
    assert TAJNA_A not in spojeno and TAJNA_B not in spojeno
    assert not [f for ns, f in indeks.videni_filteri if ns == NS_A], \
        "namespace vlasnika je pretražen bez autorizacije"


def test_f01_prazna_lista_ne_znaci_bez_ogranicenja():
    """Prazan filter je u Pinecone-u 'bez ograničenja'. Korisnik bez ijednog
    predmeta ne sme da dobije SVE."""
    assert filter_za_namespace_vlasnika([], ["case_doc"]) is None
    docs, meta, _ = _pretrazi(dozvoljeni=[])
    spojeno = "\n".join(docs) + "\n" + str(meta.get("doc_passages", ""))
    assert TAJNA_A not in spojeno and TAJNA_B not in spojeno


def test_f01_filter_nikad_nije_prazan_dict():
    f = filter_za_namespace_vlasnika(["p1"], ["case_doc"])
    assert f and f["predmet_id"]["$in"] == ["p1"]
    assert f["type"]["$in"] == ["case_doc"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. IZVOR AUTORIZACIJE — OGLEDALO get_predmet
# ═══════════════════════════════════════════════════════════════════════════

class _FakeSupaACL:
    def __init__(self, predmeti, delegacije, puca_delegacije=False):
        self._p, self._d, self._puca = predmeti, delegacije, puca_delegacije

    def table(self, ime):
        spolja = self

        class _Q:
            def __init__(self):
                self.ime, self.uslovi = ime, {}

            def select(self, *a, **k):
                return self

            def eq(self, k, v):
                self.uslovi[k] = v
                return self

            def execute(self):
                if self.ime == "predmeti":
                    d = [r for r in spolja._p if r["user_id"] == self.uslovi.get("user_id")]
                elif self.ime == "predmet_delegiranja":
                    if spolja._puca:
                        raise RuntimeError("tabela nedostupna")
                    d = [r for r in spolja._d
                         if r["na_user_id"] == self.uslovi.get("na_user_id")
                         and r["status"] == self.uslovi.get("status")]
                else:
                    d = []
                return MagicMock(data=d)
        return _Q()


def test_acl_vraca_svoje_i_delegirane_predmete():
    supa = _FakeSupaACL(
        predmeti=[{"id": "p1", "user_id": "u1"}, {"id": "p2", "user_id": "u2"}],
        delegacije=[{"predmet_id": "p2", "na_user_id": "u1", "status": "aktivno"}],
    )
    assert dozvoljeni_predmeti(supa, "u1") == ["p1", "p2"]


def test_acl_neaktivna_delegacija_ne_daje_pristup():
    supa = _FakeSupaACL(
        predmeti=[{"id": "p1", "user_id": "u1"}, {"id": "p2", "user_id": "u2"}],
        delegacije=[{"predmet_id": "p2", "na_user_id": "u1", "status": "opozvano"}],
    )
    assert dozvoljeni_predmeti(supa, "u1") == ["p1"]


def test_acl_clanstvo_u_kancelariji_nije_osnov():
    """Srž F-01, izražena kao ugovor: kolega iz iste firme nema pristup."""
    supa = _FakeSupaACL(
        predmeti=[{"id": "p-kolega", "user_id": "kolega"}],
        delegacije=[],
    )
    assert dozvoljeni_predmeti(supa, "u1") == []


def test_acl_pad_delegacija_suzava_a_ne_siri():
    supa = _FakeSupaACL(
        predmeti=[{"id": "p1", "user_id": "u1"}],
        delegacije=[{"predmet_id": "p9", "na_user_id": "u1", "status": "aktivno"}],
        puca_delegacije=True,
    )
    assert dozvoljeni_predmeti(supa, "u1") == ["p1"], "ispad tabele sme samo da suzi skup"


def test_acl_pad_predmeta_dize_izuzetak_a_ne_tiho_prazno():
    """Ako glavna tabela padne, pozivalac mora da zna. Tiha prazna lista bi
    izgledala kao 'korisnik nema predmete'."""
    class _Puca:
        def table(self, *a, **k):
            raise RuntimeError("baza nedostupna")
    with pytest.raises(Exception):
        dozvoljeni_predmeti(_Puca(), "u1")


# ═══════════════════════════════════════════════════════════════════════════
# 5. KONTROLA NAD SAMIM TEST ALATOM
# ═══════════════════════════════════════════════════════════════════════════

def test_lazni_indeks_stvarno_primenjuje_filter():
    """Bez ovoga se svim testovima iznad ne veruje — tačno mana zbog koje
    postojeći `mock_index` u repou ne dokazuje nijedno bezbednosno svojstvo."""
    ix = _LazniIndeks(_svet_vektora())
    svi = ix.query(namespace=NS_A, filter=None, top_k=10)
    assert len(svi.matches) == 2, "bez filtera se vide oba predmeta"
    samo_a = ix.query(namespace=NS_A, top_k=10,
                      filter={"predmet_id": {"$in": ["pred-A"]}})
    assert len(samo_a.matches) == 1
    assert TAJNA_A in samo_a.matches[0].metadata["text"]
    with pytest.raises(AssertionError):
        ix.query(namespace=NS_A, top_k=10, filter={"predmet_id": {"$ne": "x"}})


# ═══════════════════════════════════════════════════════════════════════════
# 6. PINE-01 — ŠTA BRISANJE JESTE, A ŠTA NIJE
# ═══════════════════════════════════════════════════════════════════════════
#
# Deterministička identifikacija vektora dokumenta NE POSTOJI: `chunk_id` je
# goli `uuid4` (`uploaded_doc/chunker.py:157`), `document_id` nije ni u jednoj
# metadata, i nema kolone sa ID-evima vektora. Zato brisanje NIJE implementirano
# u ovom sprintu — §8 mandata to izričito zabranjuje bez identifikacije.
#
# Ali JEDNO svojstvo se dobija besplatno iz načina na koji je F-01 zatvoren, i
# vredi ga zaključati testom: pošto autorizacija dolazi iz TRENUTNOG stanja baze
# (`dozvoljeni_predmeti`), a ne iz metapodataka vektora, brisanje predmeta iz
# baze čini njegove vektore NEDOHVATLJIVIM — i pre nego što ijedan vektor bude
# obrisan.
#
# To NIJE brisanje i ne zadovoljava GDPR čl. 17. Podatak i dalje postoji kod
# Pinecone-a. Zatvara samo napad „obrisan dokument je i dalje pretraživ".

def test_pine01_obrisan_predmet_postaje_nedohvatljiv_iako_vektori_ostaju():
    """§10.1-2 i §13: autorizacija iz trenutnog stanja, ne iz istorije.

    Vektori za `pred-B` i dalje FIZIČKI postoje u lažnom indeksu — tačno kao
    orphan vektori izmereni u produkciji. Ali `pred-B` više nije u skupu
    autorizovanih, pa ne može da se vrati.
    """
    # Pre "brisanja": oba predmeta autorizovana → oba se vide.
    docs, meta, _ = _pretrazi(dozvoljeni=["pred-A", "pred-B"])
    assert TAJNA_B in "\n".join(docs) + str(meta.get("doc_passages", ""))

    # Posle "brisanja" pred-B iz baze: vektori NISU dirani, ali ACL ih ne zna.
    docs, meta, indeks = _pretrazi(dozvoljeni=["pred-A"])
    spojeno = "\n".join(docs) + str(meta.get("doc_passages", ""))
    assert TAJNA_B not in spojeno, "obrisan predmet je i dalje pretraživ"
    assert TAJNA_A in spojeno, "brat-predmet mora da preživi"
    # Dokaz da vektor i dalje postoji — dakle svojstvo dolazi od ACL-a, a ne
    # od toga što je test slučajno uklonio podatak.
    assert any(m.get("predmet_id") == "pred-B" for _, m, _ in indeks.vektori)


def test_pine01_orphan_vektor_bez_predmeta_u_bazi_nije_dohvatljiv():
    """Izmereno u produkciji: 6 `pred_*` namespace-ova sa 30 vektora nema
    nijedan odgovarajući red u bazi. Takav vektor ne sme da bude dohvatljiv
    ni pod kojim uslovima."""
    docs, meta, _ = _pretrazi(dozvoljeni=["pred-A"])
    spojeno = "\n".join(docs) + str(meta.get("doc_passages", ""))
    for tajna in (TAJNA_B, TAJNA_T2):
        assert tajna not in spojeno


def test_pine01_ponovljeno_brisanje_je_idempotentno_na_nivou_acl_a():
    """§9: brisanje već obrisanog mora biti NO-OP, ne greška."""
    for _ in range(3):
        docs, meta, _ = _pretrazi(dozvoljeni=["pred-A"])
        assert TAJNA_B not in "\n".join(docs) + str(meta.get("doc_passages", ""))
