# -*- coding: utf-8 -*-
"""
BETA-DATA-ID-01 — DETERMINISTIČKI IDENTITET VEKTORA.

ŠTA JE BILO

`uploaded_doc/chunker.py:157` daje `chunk_id = str(uuid.uuid4())`, a
`ingest.py` je baš to koristio kao Pinecone `id`. Tri posledice, sve merene u
sprintu 003:

  1. ponovni upload istog fajla → potpuno novi ID-evi → **duplikati**
  2. nema načina da se nađu svi vektori jednog dokumenta → **nema brisanja**
  3. nema veze vektor → red u bazi → **nema orphan detekcije**

Izmereno u produkciji: 43 dokumenta u bazi, 6 `pred_*` namespace-ova sa 30
vektora, **presek 0**. Nijedan vektor se nije mogao pripisati nijednom
dokumentu.

MODEL

    {scope}__{verzija}__k{chunk_schema}_c{chunk_index}

`scope` je granica vlasništva i brisanja (`predmet_id`, inače `session_id`);
`verzija` je SHA-256 samog fajla; `chunk_schema` je verzija algoritma deljenja.

NASLEDNIK, NE IZUM — obrazac `{scope}_c{index}` već radi u
`routers/law_upload.py:126`. Ovaj sprint mu dodaje verziju sadržaja i verziju
šeme, bez kojih ne razlikuje dve verzije istog dokumenta.

HEŠ NIJE AUTORIZACIJA (RULE 4). `verzija` služi identitetu i integritetu.
Kapija ostaje `api.py::get_predmet` i `shared/rag_acl.py`. Zato je `scope` deo
ID-a: dva korisnika sa ISTIM fajlom dobijaju RAZLIČITE ID-eve.
"""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "founder@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from shared.vector_identity import (  # noqa: E402
    CHUNK_SCHEMA_VERSION,
    NedovoljanIdentitet,
    canonical_vector_id,
    metapodaci_identiteta,
    prefiks_dokumenta,
    verzija_sadrzaja,
)
from uploaded_doc.ingest import ingest_session  # noqa: E402
from uploaded_doc.schema import ChunkingManifest, UploadedDocChunk  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# LAŽNI PINECONE KOJI SE PONAŠA KAO PRAVI: upsert PREPISUJE po ID-u
# ═══════════════════════════════════════════════════════════════════════════

class _LazniIndeks:
    """Ključna semantika za ovaj sprint: `upsert` je UPSERT — isti `id`
    prepisuje, ne dodaje. Bez toga se idempotentnost ne može dokazati."""

    def __init__(self):
        self.prostor = {}          # namespace -> {id: metadata}
        self.pozivi = 0

    def upsert(self, vectors, namespace):
        self.pozivi += 1
        ns = self.prostor.setdefault(namespace, {})
        for v in vectors:
            ns[v["id"]] = v["metadata"]

    def broj(self, namespace):
        return len(self.prostor.get(namespace, {}))

    def idevi(self, namespace):
        return sorted(self.prostor.get(namespace, {}))


def _manifest(n: int, sha: str = "a" * 64, tekst: str = "Pasus") -> ChunkingManifest:
    sada = datetime.now(tz=timezone.utc)
    return ChunkingManifest(
        source_filename="ugovor.pdf", source_format="pdf", source_sha256=sha,
        is_scanned=False, total_chunks=n, chunk_mode_used="recursive",
        article_labels_detected=[], token_p10=10, token_p50=10, token_p90=10,
        chunks=[
            UploadedDocChunk(
                chunk_id=f"nasumicno-{os.urandom(4).hex()}",  # NAMERNO nasumičan
                session_id="s", source_filename="ugovor.pdf", source_format="pdf",
                source_sha256=sha, chunk_index=i, chunk_mode="recursive",
                article_label=None, text=f"{tekst} {i}", token_count=10,
                char_count=20, created_at=sada,
            )
            for i in range(n)
        ],
    )


def _ingest(n=3, sha="a" * 64, predmet_id=None, session_id="sess-1",
            ns="kancelarija_A", indeks=None, n_vektora=None):
    indeks = indeks or _LazniIndeks()
    ugradnje = MagicMock()
    ugradnje.embed_documents.return_value = [
        [0.0] * 3072 for _ in range(n if n_vektora is None else n_vektora)
    ]
    extra = {"predmet_id": predmet_id} if predmet_id else None
    with patch("uploaded_doc.ingest._get_embeddings_client", return_value=ugradnje), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=indeks):
        broj = ingest_session(_manifest(n, sha), session_id,
                              namespace_override=ns, extra_metadata=extra)
    return broj, indeks


# ═══════════════════════════════════════════════════════════════════════════
# 1. UGOVOR ID-a (§5)
# ═══════════════════════════════════════════════════════════════════════════

def test_id01_isti_ulaz_daje_isti_id():
    """Determinizam je celo pitanje sprinta."""
    a = canonical_vector_id("pred-1", "abc123", 7)
    b = canonical_vector_id("pred-1", "abc123", 7)
    assert a == b


def test_id01_nezavisan_od_procesa():
    """`uuid4` je bio zavisan od poziva. Novi ID sme da zavisi SAMO od ulaza —
    ne od vremena, procesa ni broja pokušaja."""
    import subprocess
    kod = ("import sys; sys.path.insert(0, r'%s');"
           "from shared.vector_identity import canonical_vector_id;"
           "print(canonical_vector_id('pred-1','abc123',7))"
           % os.path.join(os.path.dirname(__file__), ".."))
    izlaz = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True)
    assert izlaz.stdout.strip() == canonical_vector_id("pred-1", "abc123", 7)


@pytest.mark.parametrize("a,b,zasto", [
    (("pred-1", "sha", 0), ("pred-2", "sha", 0), "drugi predmet"),
    (("pred-1", "sha1", 0), ("pred-1", "sha2", 0), "druga verzija sadržaja"),
    (("pred-1", "sha", 0), ("pred-1", "sha", 1), "drugi chunk"),
])
def test_id01_razlicit_ulaz_daje_razlicit_id(a, b, zasto):
    assert canonical_vector_id(*a) != canonical_vector_id(*b), zasto


def test_id01_isti_sadrzaj_razliciti_tenanti_daju_razlicite_id():
    """RULE 12 — NAJVAŽNIJI BEZBEDNOSNI TEST U FAJLU.

    Dva korisnika otpreme DOSLOVNO isti fajl. Heš je identičan. Kad bi ID bio
    samo heš sadržaja, njihovi vektori bi se prepisali međusobno — jedan bi
    dobio dokument drugog. `scope` to sprečava.
    """
    sadrzaj = b"isti ugovor, dve kancelarije"
    v = verzija_sadrzaja(sadrzaj)
    assert canonical_vector_id("pred-tenantA", v, 0) != canonical_vector_id("pred-tenantB", v, 0)


def test_id01_promena_chunking_seme_daje_novi_identitet():
    """§6: ako se promeni algoritam deljenja, `chunk_index` menja ZNAČENJE.
    Bez verzije šeme bi novi chunk-ovi prepisali stare kao da su isti."""
    assert canonical_vector_id("p", "v", 0, chunk_schema=1) != \
           canonical_vector_id("p", "v", 0, chunk_schema=2)


def test_id01_verzija_sadrzaja_je_stabilna_i_osetljiva():
    assert verzija_sadrzaja("tekst") == verzija_sadrzaja(b"tekst")
    assert verzija_sadrzaja("tekst") != verzija_sadrzaja("tekst ")


# ═══════════════════════════════════════════════════════════════════════════
# 2. FAIL-CLOSED (RULE 6)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("args", [
    ("", "sha", 0), ("pred", "", 0), ("   ", "sha", 0), ("pred", "sha", -1),
])
def test_id01_nedovoljan_identitet_dize_izuzetak(args):
    with pytest.raises(NedovoljanIdentitet):
        canonical_vector_id(*args)


def test_id01_manifest_bez_sha_ne_upisuje_nista():
    """RULE 6 doslovno: bez identiteta se vektor NE upisuje."""
    indeks = _LazniIndeks()
    with pytest.raises(NedovoljanIdentitet):
        _ingest(sha="", indeks=indeks)
    assert indeks.pozivi == 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. IDEMPOTENTNOST (§8) — SRŽ MISIJE
# ═══════════════════════════════════════════════════════════════════════════

def test_id01_ponovljen_ingest_NE_povecava_broj_vektora():
    """§8 doslovno: INGEST #1 → N, INGEST #2 istog ulaza → i dalje N, ne 2N.

    Ovo je bilo NEMOGUĆE dok je ID bio `uuid4`.
    """
    indeks = _LazniIndeks()
    _ingest(n=5, indeks=indeks)
    prvi = indeks.broj("kancelarija_A")
    assert prvi == 5

    _ingest(n=5, indeks=indeks)   # isti fajl, novi upload
    assert indeks.broj("kancelarija_A") == 5, "ponovni ingest je duplirao vektore"


def test_id01_ponovljen_ingest_daje_IDENTICNE_ideve():
    _, i1 = _ingest(n=4)
    _, i2 = _ingest(n=4)
    assert i1.idevi("kancelarija_A") == i2.idevi("kancelarija_A")


def test_id01_izmenjen_dokument_pravi_NOVU_verziju_a_ne_prepisuje():
    """RULE 9: nova verzija ne sme tiho da pojede staru — obe moraju ostati
    jednoznačno adresabilne dok se stara izričito ne obriše."""
    indeks = _LazniIndeks()
    _ingest(n=3, sha="a" * 64, indeks=indeks)
    _ingest(n=3, sha="b" * 64, indeks=indeks)
    assert indeks.broj("kancelarija_A") == 6, "verzije se ne smeju prepisati"


def test_id01_isti_fajl_u_dva_predmeta_ostaje_odvojen():
    indeks = _LazniIndeks()
    _ingest(n=2, predmet_id="pred-A", indeks=indeks)
    _ingest(n=2, predmet_id="pred-B", indeks=indeks)
    assert indeks.broj("kancelarija_A") == 4


# ═══════════════════════════════════════════════════════════════════════════
# 4. BRISANJE POSTAJE MOGUĆE (§12) — ovo je ono što odblokira PINE-01
# ═══════════════════════════════════════════════════════════════════════════

def test_id01_prefiks_izdvaja_TACNO_jedan_dokument():
    """Bez ovoga `PINE-01` ostaje blokiran: najuži izvodljiv filter bio je ceo
    predmet. Sa prefiksom se cilja tačno jedna verzija jednog dokumenta."""
    indeks = _LazniIndeks()
    _ingest(n=3, sha="a" * 64, predmet_id="pred-A", indeks=indeks)
    _ingest(n=3, sha="b" * 64, predmet_id="pred-A", indeks=indeks)
    _ingest(n=3, sha="c" * 64, predmet_id="pred-B", indeks=indeks)

    pref = prefiks_dokumenta("pred-A", "a" * 32)
    pogodjeni = [i for i in indeks.idevi("kancelarija_A") if i.startswith(pref)]
    assert len(pogodjeni) == 3, "prefiks ne izdvaja tačno jedan dokument"

    ostali = [i for i in indeks.idevi("kancelarija_A") if not i.startswith(pref)]
    assert len(ostali) == 6, "brat-dokument i tuđi predmet moraju preživeti"


def test_id01_prefiks_jednog_tenanta_ne_pogadja_drugog():
    """Brisanje po prefiksu ne sme da pređe granicu predmeta."""
    indeks = _LazniIndeks()
    _ingest(n=2, sha="a" * 64, predmet_id="pred-A", indeks=indeks)
    _ingest(n=2, sha="a" * 64, predmet_id="pred-B", indeks=indeks)
    pref = prefiks_dokumenta("pred-A", "a" * 32)
    assert len([i for i in indeks.idevi("kancelarija_A") if i.startswith(pref)]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 5. METAPODACI (§7) — minimalni, bez PII
# ═══════════════════════════════════════════════════════════════════════════

def test_id01_metapodaci_ne_sadrze_PII():
    m = metapodaci_identiteta("pred-1", "abc", 0, predmet_id="pred-1")
    spojeno = " ".join(str(v).lower() for v in m.values()) + " " + " ".join(m)
    for zabranjeno in ("jmbg", "email", "e-mail", "adresa", "ime_klijenta", "text", "sadrzaj"):
        assert zabranjeno not in spojeno


def test_id01_identitet_stize_u_metapodatke_vektora():
    _, indeks = _ingest(n=2, predmet_id="pred-A")
    meta = list(indeks.prostor["kancelarija_A"].values())[0]
    assert meta["vx_scope"] == "pred-A"
    assert meta["vx_chunk_schema"] == CHUNK_SCHEMA_VERSION
    assert meta["vx_verzija"]


def test_id01_pozivalac_ne_moze_pregaziti_identitet():
    """`extra_metadata` se primenjuje PRE identiteta, pa ga ne može oboriti."""
    indeks = _LazniIndeks()
    ugradnje = MagicMock()
    ugradnje.embed_documents.return_value = [[0.0] * 3072]
    with patch("uploaded_doc.ingest._get_embeddings_client", return_value=ugradnje), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=indeks):
        ingest_session(_manifest(1), "s", namespace_override="ns",
                       extra_metadata={"predmet_id": "pred-A", "vx_scope": "LAZ"})
    assert list(indeks.prostor["ns"].values())[0]["vx_scope"] == "pred-A"


# ═══════════════════════════════════════════════════════════════════════════
# 6. DELIMIČAN EMBEDDING (§9) — i dalje blokiran posle uvođenja identiteta
# ═══════════════════════════════════════════════════════════════════════════

def test_id01_delimican_embedding_i_dalje_ne_upisuje_nista():
    indeks = _LazniIndeks()
    with pytest.raises(RuntimeError):
        _ingest(n=10, n_vektora=6, indeks=indeks)
    assert indeks.pozivi == 0


# ═══════════════════════════════════════════════════════════════════════════
# 7. KONTROLA NAD TEST ALATOM
# ═══════════════════════════════════════════════════════════════════════════

def test_lazni_indeks_prepisuje_po_idu_kao_pravi_pinecone():
    """Bez ove semantike test idempotentnosti ne bi značio ništa."""
    ix = _LazniIndeks()
    ix.upsert([{"id": "x", "metadata": {"a": 1}}], namespace="n")
    ix.upsert([{"id": "x", "metadata": {"a": 2}}], namespace="n")
    assert ix.broj("n") == 1
    assert ix.prostor["n"]["x"]["a"] == 2


def test_chunk_id_je_i_dalje_nasumican_ali_vise_nije_identitet_vektora():
    """Dokaz da determinizam dolazi od novog modela, a NE od toga što je test
    slučajno koristio stabilne `chunk_id`-eve: manifest ih namerno pravi
    nasumično, a ID-evi vektora su ipak identični."""
    m1, m2 = _manifest(2), _manifest(2)
    assert {c.chunk_id for c in m1.chunks} & {c.chunk_id for c in m2.chunks} == set()
    _, i1 = _ingest(n=2)
    _, i2 = _ingest(n=2)
    assert i1.idevi("kancelarija_A") == i2.idevi("kancelarija_A")


# ═══════════════════════════════════════════════════════════════════════════
# 8. IDENTITET ↔ AUTORIZACIJA — veza koju mutacija C otkriva
# ═══════════════════════════════════════════════════════════════════════════
#
# Mutacija „ukloni vezivanje za tenanta" prvo NIJE oborila nijedan test, jer
# `predmet_id` u metapodatke stiže i kroz `extra_metadata` — pa je provera bila
# slepa za to KOJIM putem binding nestane. §14 nalaže da se takav test popravi,
# a ne da se mutacija proglasi bezopasnom.
#
# Ovaj test meri POSLEDICU umesto prisustva polja: da li upisan vektor prolazi
# kroz PRAVI ACL filter iz `shared/rag_acl.py`. Ako tenant binding nestane bilo
# gde na putu, filter ga više ne pogađa i test pada.

def _prolazi_filter(meta: dict, filter_: dict) -> bool:
    for polje, uslov in (filter_ or {}).items():
        v = meta.get(polje)
        if isinstance(uslov, dict) and "$in" in uslov:
            if v not in uslov["$in"]:
                return False
        elif v != uslov:
            return False
    return True


def test_id01_upisan_vektor_prolazi_kroz_pravi_ACL_filter_svog_predmeta():
    """Bez tenant bindinga vektor postaje nevidljiv sopstvenom vlasniku —
    ili, ako se ACL ikad olabavi, vidljiv tuđem."""
    from shared.rag_acl import filter_za_namespace_vlasnika

    _, indeks = _ingest(n=2, predmet_id="pred-A")
    meta = list(indeks.prostor["kancelarija_A"].values())[0]
    meta.setdefault("type", "case_doc")

    f_svoj = filter_za_namespace_vlasnika(["pred-A"], ["case_doc"])
    assert _prolazi_filter(meta, f_svoj), (
        "vektor ne prolazi ACL filter sopstvenog predmeta — tenant binding je "
        "izgubljen negde na putu identitet → metapodaci"
    )


def test_id01_upisan_vektor_NE_prolazi_filter_tudjeg_predmeta():
    from shared.rag_acl import filter_za_namespace_vlasnika

    _, indeks = _ingest(n=2, predmet_id="pred-A")
    meta = list(indeks.prostor["kancelarija_A"].values())[0]
    meta.setdefault("type", "case_doc")

    f_tudji = filter_za_namespace_vlasnika(["pred-B"], ["case_doc"])
    assert not _prolazi_filter(meta, f_tudji)


def test_id01_scope_u_idu_i_predmet_u_metapodacima_se_slazu():
    """Dva nezavisna nosioca istog fakta moraju da se poklapaju — inače
    brisanje po prefiksu i pretraga po filteru gađaju različite skupove."""
    _, indeks = _ingest(n=1, predmet_id="pred-A")
    vid = indeks.idevi("kancelarija_A")[0]
    meta = indeks.prostor["kancelarija_A"][vid]
    assert vid.startswith("pred-A__")
    assert meta["predmet_id"] == "pred-A"
    assert meta["vx_scope"] == "pred-A"


# ═══════════════════════════════════════════════════════════════════════════
# 9. REGRESIJA KOJU JE UVEO OVAJ SPRINT
# ═══════════════════════════════════════════════════════════════════════════
#
# Forenzički inventar je uhvatio da `routers/drafting.py` prosleđuje
# `"source_sha256": ""`. Fail-closed kapija iz RULE 6 na to diže
# `NedovoljanIdentitet`, a `drafting.py` taj izuzetak GUTA i vraća `False` —
# pa bi promocija odobrenog nacrta tiho prestala da radi, bez ijedne poruke.
#
# Popravka nije bila da se kapija olabavi, nego da nacrt dobije stvarnu verziju:
# heš sopstvenog teksta.

def test_id01_promocija_nacrta_stvarno_upisuje_vektore():
    """Vozi PRAVU `_promote_staged_draft_to_pinecone`, ne njen izvor.

    §14 izričito zabranjuje `assert "..." in source` kao dokaz. Ovde se meri
    ishod: da li je promocija upisala vektore i da li im je identitet pun.
    Sa praznim `source_sha256` fail-closed kapija diže izuzetak, `drafting.py`
    ga guta i vraća `False` — pa test pada, tiho baš kao što bi i produkcija.
    """
    import asyncio as _aio

    import routers.drafting as d

    indeks = _LazniIndeks()
    ugradnje = MagicMock()
    ugradnje.embed_documents.side_effect = lambda t: [[0.0] * 3072 for _ in t]

    supa = MagicMock()
    supa.table.return_value.select.return_value.eq.return_value.order.return_value         .limit.return_value.execute.return_value = MagicMock(data=[{"redni_broj": 0}])
    supa.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "dok-1"}])
    supa.table.return_value.update.return_value.eq.return_value.execute.return_value =         MagicMock(data=[])

    red = {
        "id": "stg-1", "predmet_id": "pred-A", "user_id": "u1",
        "kancelarija_id": None, "tekst": "Tuženi je dužan da isplati. " * 30,
        "naziv": "Tužba", "tip": "tuzba",
    }

    with patch("uploaded_doc.ingest._get_embeddings_client", return_value=ugradnje),          patch("uploaded_doc.ingest._get_pinecone_index", return_value=indeks):
        ok = _aio.run(d._promote_staged_draft_to_pinecone(supa, red))

    assert ok is True, "promocija odobrenog nacrta je pala"
    assert indeks.pozivi > 0, "nijedan vektor nije upisan"
    vid = indeks.idevi("user_u1")[0] if indeks.prostor.get("user_u1")         else indeks.idevi(next(iter(indeks.prostor)))[0]
    assert vid.startswith("pred-A__"), f"nacrt nema scope predmeta u ID-u: {vid}"
    assert "____" not in vid, f"verzija nacrta je prazna: {vid}"


def test_id01_verzija_nacrta_je_stabilna_za_isti_tekst():
    """Ponovna promocija istog teksta mora dati iste ID-eve, inače se nacrti
    gomilaju kao duplikati pri svakom odobravanju."""
    tekst = "Tuženi je dužan da isplati iznos od 100.000 dinara."
    assert verzija_sadrzaja(tekst) == verzija_sadrzaja(tekst)
    assert verzija_sadrzaja(tekst) != verzija_sadrzaja(tekst + " ")
    assert canonical_vector_id("pred-1", verzija_sadrzaja(tekst), 0) == \
           canonical_vector_id("pred-1", verzija_sadrzaja(tekst), 0)
