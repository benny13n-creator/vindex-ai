# -*- coding: utf-8 -*-
"""
BETA-DATA-CONFIDENTIALITY-004 — „PRIMLJEN" NIJE „INDEKSIRAN".

PITANJE SPRINTA

Može li Vindex pouzdano razlikovati „fajl je primljen" od „fajl je stvarno
ingestovan i spreman za AI pretragu"?

ŠTA JE BILO — dva puta lažnog uspeha, oba merena

FS-001 — USPEH SE PRETPOSTAVLJAO, NE DOKAZIVAO.
`ingest_session()` vraća broj stvarno upisanih vektora. **Nijedan pozivalac ga
nikad nije proverio.** `_pinecone_ok` je ostajao `True` samo zato što izuzetak
nije podignut. Dokument upisan delimično nosio je status `indeksirano`.

FS-002 — `zip()` JE TIHO SKRAĆIVAO.
`zip(manifest.chunks, vectors_raw)` staje na kraćoj sekvenci. Ako embedding
provajder vrati manje vektora nego što ima chunk-ova, upsert-uje se podskup,
`len(records)` vrati taj manji broj — i niko ne primeti. Delimičan ingest
prijavljen kao potpun, tačno §5.F mandata.

FS-003 — KLASIFIKATOR KVOTE JE BIO PREŠIROK.
`"storage" in str(exc).lower()` je svaku grešku čija poruka sadrži „storage" —
uključujući greške Supabase Storage-a — pretvarao u „kvotu", pa je dokument
završavao kao `sacuvano` umesto da podigne grešku.

ZAŠTO TESTOVI VOZE PRAVE FUNKCIJE

Mandat §5 zabranjuje testove koji sami rekonstruišu produkcijsku granu i
`MagicMock` lance koji ostaju zeleni kad se writer ukloni. Zato:
  · `ingest_session` se poziva STVARNO, sa lažnim indeksom koji BELEŽI upsert-e
  · odluka o statusu je izdvojena u `ingest_je_potpun` / `je_kvota_greska`,
    pa se testira produkcijska funkcija, a ne njena kopija u testu
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

from uploaded_doc.ingest import (  # noqa: E402
    ingest_je_potpun,
    ingest_session,
    je_kvota_greska,
)
from uploaded_doc.schema import ChunkingManifest, UploadedDocChunk  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# LAŽNI PINECONE KOJI STVARNO BELEŽI UPIS
# ═══════════════════════════════════════════════════════════════════════════

class _LazniIndeks:
    """Beleži svaki upsert. `pad_na_batchu` obara N-ti batch (0-indeksiran),
    pri čemu prethodni batch-evi OSTAJU upisani — tačno kao u produkciji."""

    def __init__(self, pad_na_batchu=None, greska=None):
        self.upisano = []          # [(namespace, [id, ...])]
        self.pozivi = 0
        self._pad = pad_na_batchu
        self._greska = greska or RuntimeError("Pinecone nedostupan")

    def upsert(self, vectors, namespace):
        if self._pad is not None and self.pozivi == self._pad:
            self.pozivi += 1
            raise self._greska
        self.pozivi += 1
        self.upisano.append((namespace, [v["id"] for v in vectors]))

    @property
    def ukupno_vektora(self):
        return sum(len(ids) for _, ids in self.upisano)


def _manifest(n: int) -> ChunkingManifest:
    sada = datetime.now(tz=timezone.utc)
    chunks = [
        UploadedDocChunk(
            chunk_id=f"chunk-{i:04d}", session_id="sess-1",
            source_filename="ugovor.pdf", source_format="pdf",
            source_sha256="abc", chunk_index=i, chunk_mode="recursive",
            article_label=None, text=f"Pasus broj {i}.", token_count=10,
            char_count=20, created_at=sada,
        )
        for i in range(n)
    ]
    return ChunkingManifest(
        source_filename="ugovor.pdf", source_format="pdf", source_sha256="abc",
        is_scanned=False, total_chunks=n, chunk_mode_used="recursive",
        article_labels_detected=[], token_p10=10, token_p50=10, token_p90=10,
        chunks=chunks,
    )


def _pokreni(n_chunks, n_vektora=None, indeks=None):
    """Vozi PRAVI `ingest_session`. `n_vektora` različit od `n_chunks`
    simulira delimičan odgovor embedding provajdera."""
    indeks = indeks or _LazniIndeks()
    ugradnje = MagicMock()
    ugradnje.embed_documents.return_value = [
        [0.0] * 3072 for _ in range(n_chunks if n_vektora is None else n_vektora)
    ]
    with patch("uploaded_doc.ingest._get_embeddings_client", return_value=ugradnje), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=indeks):
        broj = ingest_session(_manifest(n_chunks), "sess-1",
                              namespace_override="kancelarija_A")
    return broj, indeks


# ═══════════════════════════════════════════════════════════════════════════
# A — PUN USPEH
# ═══════════════════════════════════════════════════════════════════════════

def test_a_pun_uspeh_vraca_tacan_broj_i_stvarno_upisuje():
    broj, indeks = _pokreni(120)
    assert broj == 120
    assert indeks.ukupno_vektora == 120, "vektori nisu stvarno upisani"
    assert ingest_je_potpun(broj, 120) is True


# ═══════════════════════════════════════════════════════════════════════════
# F — DELIMIČAN UPIS NE SME BITI PRIJAVLJEN KAO POTPUN
# ═══════════════════════════════════════════════════════════════════════════

def test_f_embedding_vratio_manje_vektora_dize_gresku():
    """FS-002. Ranije je `zip` tiho odsecao razliku i vraćao manji broj kao da
    je sve u redu."""
    with pytest.raises(RuntimeError, match="delimičan ingest"):
        _pokreni(100, n_vektora=60)


def test_f_nijedan_vektor_nije_upisan_kad_se_neslaganje_otkrije():
    """Kapija mora da stoji PRE upisa — inače bi 60 vektora završilo u
    Pinecone-u kao orphan."""
    indeks = _LazniIndeks()
    with pytest.raises(RuntimeError):
        _pokreni(100, n_vektora=60, indeks=indeks)
    assert indeks.ukupno_vektora == 0


def test_f_pad_batcha_u_sredini_dize_gresku_a_ne_delimican_uspeh():
    """Pad 2. batch-a od 3: prvi batch je VEĆ u Pinecone-u. Funkcija mora da
    digne izuzetak, da pozivalac ne bi tvrdio da je dokument indeksiran."""
    indeks = _LazniIndeks(pad_na_batchu=1)
    with pytest.raises(RuntimeError):
        _pokreni(120, indeks=indeks)
    assert indeks.ukupno_vektora == 50, "prvi batch jeste upisan — to su orphan vektori"


# ═══════════════════════════════════════════════════════════════════════════
# B / C — KVOTA vs STVARNA GREŠKA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("poruka", [
    "429 Too Many Requests",
    "Max serverless index storage size exceeded",
    "quota exceeded for index",
    "Storage is full",
])
def test_b_kvota_se_prepoznaje(poruka):
    assert je_kvota_greska(RuntimeError(poruka)) is True


@pytest.mark.parametrize("poruka", [
    "Supabase storage upload failed: bucket not found",
    "invalid storage_path for document",
    "connection reset by peer",
    "OpenAI API key invalid",
    "dimension mismatch: expected 3072",
])
def test_c_stvarna_greska_se_NE_proglasava_kvotom(poruka):
    """FS-003 — SRŽ.

    Stari klasifikator (`"storage" in poruka.lower()`) je prva dva slučaja
    proglašavao kvotom, pa je dokument tiho završavao kao 'sacuvano' umesto da
    podigne 500. Korisnik bi video „primljeno", a uzrok bi ostao nevidljiv.
    """
    assert je_kvota_greska(RuntimeError(poruka)) is False


# ═══════════════════════════════════════════════════════════════════════════
# H — NEISPRAVNO STANJE NIKAD NIJE USPEH
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("upisano,ocekivano", [
    (0, 5), (3, 5), (5, 6), (0, 0), (5, 0), (-1, 5), (5, -1),
])
def test_h_nepotpun_ili_besmislen_broj_nije_uspeh(upisano, ocekivano):
    assert ingest_je_potpun(upisano, ocekivano) is False


def test_h_nula_ocekivanih_nije_trivijalan_uspeh():
    """Dokument bez ijednog chunk-a nije „uspešno indeksiran u celosti" —
    on uopšte nije indeksiran."""
    assert ingest_je_potpun(0, 0) is False


# ═══════════════════════════════════════════════════════════════════════════
# I — PONOVLJEN INGEST (dokumentuje ID-01, ne rešava ga)
# ═══════════════════════════════════════════════════════════════════════════

def test_i_ponovljen_ingest_je_idempotentan_za_ISTI_manifest():
    """`chunk_id` je stabilan unutar jednog manifesta, pa ponovni upsert ISTIH
    ID-eva prepisuje umesto da duplira. To je Pinecone `upsert` semantika."""
    _, i1 = _pokreni(10)
    _, i2 = _pokreni(10)
    assert [ids for _, ids in i1.upisano] == [ids for _, ids in i2.upisano]


def test_i_ponovni_upload_ISTOG_fajla_pravi_duplikate_ID_01():
    """ID-01, imenovano a NE rešeno u ovom sprintu.

    `chunker.py:157` generiše `chunk_id = uuid4()` pri svakom chunk-ovanju, pa
    ponovni upload istog fajla proizvodi POTPUNO NOVE ID-eve — dupli vektori,
    bez načina da se stari nađu i obrišu. Test to zaključava kao poznato
    stanje: ako neko sutra uvede determinističku šemu, ovaj test pada i to je
    ispravan signal da ga treba obrisati.
    """
    from uploaded_doc.chunker import chunk_document
    izvor = {"source_filename": "a.txt", "source_format": "txt",
             "source_sha256": "x", "is_scanned": False, "session_id": "s1"}
    m1 = chunk_document("Neki duži tekst ugovora. " * 40, izvor)
    m2 = chunk_document("Neki duži tekst ugovora. " * 40, izvor)
    assert m1.total_chunks == m2.total_chunks
    assert {c.chunk_id for c in m1.chunks} & {c.chunk_id for c in m2.chunks} == set(), (
        "ID-01 je rešen — obriši ovaj test i implementiraj brisanje"
    )


# ═══════════════════════════════════════════════════════════════════════════
# KONTROLA NAD TEST ALATOM
# ═══════════════════════════════════════════════════════════════════════════

def test_lazni_indeks_stvarno_belezi_upis():
    """Bez ovoga ostalim testovima nema dokazne vrednosti: mock koji ništa ne
    beleži bio bi zelen i kad writer uopšte nije pozvan."""
    indeks = _LazniIndeks()
    assert indeks.ukupno_vektora == 0
    _pokreni(3, indeks=indeks)
    assert indeks.ukupno_vektora == 3
    assert indeks.upisano[0][0] == "kancelarija_A"


def test_prazan_manifest_ne_dodiruje_pinecone():
    indeks = _LazniIndeks()
    broj, _ = _pokreni(0, indeks=indeks)
    assert broj == 0
    assert indeks.pozivi == 0
    assert ingest_je_potpun(broj, 0) is False


# ═══════════════════════════════════════════════════════════════════════════
# SE-05 — ISTI zip() BUG NA JOŠ DVA PISCA
# ═══════════════════════════════════════════════════════════════════════════
#
# Protivnički pregled (§8) je našao da `uploaded_doc/ingest.py` nije jedini
# writer sa tim obrascem: `interni_stavovi.py:66` i `drafting/playbook.py:72`
# imaju identičan `zip(chunks, vectors_raw)`, i oba vraćaju skraćen broj
# KORISNIKU kao broj sačuvanih odeljaka.

def test_se05_interni_stavovi_odbija_delimican_embedding():
    import interni_stavovi as ist
    indeks = _LazniIndeks()
    ugradnje = MagicMock()
    # tri chunk-a, a provajder vraća jedan vektor
    ugradnje.embed_documents.return_value = [[0.0] * 3072]
    with patch.object(ist, "_get_embeddings_client", return_value=ugradnje), \
         patch.object(ist, "_get_pinecone_index", return_value=indeks), \
         patch.object(ist, "_chunk_text", return_value=["a", "b", "c"]):
        with pytest.raises(RuntimeError, match="delimican ingest"):
            ist.ingest_stav("u1", "Naslov", "tekst")
    assert indeks.ukupno_vektora == 0, "kapija mora stajati PRE upisa"


def test_se05_playbook_odbija_delimican_embedding():
    from drafting import playbook as pb
    indeks = _LazniIndeks()
    ugradnje = MagicMock()
    ugradnje.embed_documents.return_value = [[0.0] * 3072]
    with patch.object(pb, "_get_embeddings_client", return_value=ugradnje), \
         patch.object(pb, "_get_pinecone_index", return_value=indeks):
        import inspect
        fn = next(f for n, f in inspect.getmembers(pb, inspect.isfunction)
                  if "ingest" in n)
        sig = inspect.signature(fn)
        args = ["u1"] + ["x"] * (len(sig.parameters) - 1)
        with patch.object(pb, "_chunk_text", return_value=["a", "b", "c"], create=True):
            with pytest.raises(RuntimeError, match="delimican ingest"):
                fn(*args)
