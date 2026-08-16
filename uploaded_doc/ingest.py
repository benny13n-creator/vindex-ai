from __future__ import annotations

import logging
import os
from typing import Optional

from .schema import ChunkingManifest
from .session import expires_at_iso

logger = logging.getLogger(__name__)

_TEXT_TRUNCATE = 40_000
_TMP_NS_PREFIX = "tmp_"


def _get_pinecone_index():
    from pinecone import Pinecone
    api_key = os.environ["PINECONE_API_KEY"]
    host = os.environ.get("PINECONE_HOST", "")
    pc = Pinecone(api_key=api_key)
    if host:
        return pc.Index(host=host)
    # Fall back to first available index
    indexes = pc.list_indexes()
    index_name = indexes[0].name
    return pc.Index(index_name)


def _get_embeddings_client():
    from langchain_openai import OpenAIEmbeddings
    from app.services.retrieve import EMBEDDING_MODEL
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        dimensions=3072,
        openai_api_key=os.environ["OPENAI_API_KEY"],
    )


def ingest_session(
    manifest: ChunkingManifest,
    session_id: str,
    ttl_hours: int = 24,
    namespace_prefix: str = _TMP_NS_PREFIX,
    namespace_override: Optional[str] = None,
    extra_metadata: Optional[dict] = None,
    verzija_dokumenta_id: Optional[str] = None,
) -> int:
    """Embed chunks and upsert to a Pinecone namespace.

    Default behavior (namespace_override=None) is UNCHANGED: namespace is
    <namespace_prefix><session_id>, i to je iskljucivo za PRIVREMENE sesije
    ('tmp_', koje cleanup_expired brise po isteku TTL-a).

    NS001/FAZA 3 (BR-005): raniji tekst je ovde preporucivao stari "pred"
    prefiks za trajne dokumente predmeta. Ta sema je mrtva --
    trajni dokumenti idu kroz namespace_override=rag_owner_namespace(...), a
    nijedan `pred_*` namespace nije vise dohvatljiv (mereno: nijednom sufiks
    nije predmeti.id, a 43 takva namespace-a iz baze ne postoje u Pinecone-u).
    Preporuka je uklonjena da ne bi vratila fragmentaciju kroz dokumentaciju.

    namespace_override / extra_metadata (Institutional Learning & RAG Audit,
    2026-07-26, stavka #1): kad je namespace_override prosleđen, koristi se
    UMESTO <prefix><session_id> -- ovo je kanal za novu "vlasnik znanja"
    šemu (kancelarija_{id} / user_{id}, v. shared/kancelarija_utils.py)
    koja zamenjuje raniju per-upload nasumičnu pred_{session_id} šemu.
    extra_metadata (npr. {"predmet_id":..., "kancelarija_id":..., "type":
    "case_doc"}) se dodaje u metadata SVAKOG vektora, da omogući metadata
    filter pri pretrazi unutar deljenog namespace-a.

    Returns the number of vectors upserted. Raises on API errors.
    """
    if manifest.total_chunks == 0:
        return 0

    namespace = namespace_override if namespace_override else f"{namespace_prefix}{session_id}"
    exp_iso = expires_at_iso(ttl_hours) if (not namespace_override and namespace_prefix == _TMP_NS_PREFIX) else ""

    embeddings_client = _get_embeddings_client()
    index = _get_pinecone_index()

    texts = [c.text for c in manifest.chunks]
    vectors_raw = embeddings_client.embed_documents(texts)

    # BETA-DATA-CONFIDENTIALITY-004 / FS-002 — TIHO SKRAĆIVANJE.
    #
    # `zip()` ispod staje na kraćoj sekvenci. Ako embedding provajder vrati
    # manje vektora nego što ima chunk-ova (delimičan odgovor, prekinut batch,
    # tiho odbijanje predugačkog ulaza), `zip` to NE prijavljuje: upsert-uje se
    # podskup, `len(records)` vrati taj manji broj, i pozivalac dokument
    # proglasi indeksiranim. Dokument je tada u Pinecone-u NEPOTPUN, a u bazi
    # označen kao potpuno pretraživ.
    #
    # Ovo je delimičan ingest prijavljen kao potpun — tačno §5.F mandata.
    if len(vectors_raw) != len(manifest.chunks):
        raise RuntimeError(
            f"embedding je vratio {len(vectors_raw)} vektora za "
            f"{len(manifest.chunks)} chunk-ova — delimičan ingest se odbija"
        )

    # ── BETA-DATA-ID-01 — DETERMINISTICKI IDENTITET ─────────────────────────
    #
    # Ranije je Pinecone `id` bio `chunk.chunk_id`, a to je `uuid4()` generisan
    # pri svakom chunk-ovanju (`chunker.py:157`). Ponovni upload istog fajla
    # pravio je potpuno nove ID-eve: duplikati, nemoguce brisanje, nemoguca
    # orphan detekcija.
    #
    # Identitet se gradi iz onoga sto vec postoji, bez nove kolone i bez izmene
    # ijednog pozivaoca:
    #   scope   = `predmet_id` kad je dokument trajan (granica brisanja i
    #             vlasnistva), inace `session_id` za privremene sesije
    #   verzija = `manifest.source_sha256` -- heš SAMOG fajla
    #
    # `scope` je ono sto sprecava da isti fajl dva razlicita korisnika dobije
    # iste ID-eve (RULE 12): heš je isti, scope nije.
    from shared.vector_identity import (
        NedovoljanIdentitet,
        canonical_vector_id,
        metapodaci_identiteta,
    )
    _predmet_id = (extra_metadata or {}).get("predmet_id") or ""
    _scope = _predmet_id or session_id

    # BETA-DATA-ID-02 — VERZIJA SE IZVODI OVDE, NE UZIMA OD POZIVAOCA.
    #
    # ID-01 je verziju citao iz `manifest.source_sha256`. To je znacilo da
    # identitet dokumenta zavisi od toga sta je pisac tamo stavio -- a merenje je
    # pokazalo da su pisci stavljali RAZLICITE stvari:
    #   `api.py`       -> hes bajtova fajla
    #   `smart_intake` -> hes bajtova CELOG POSLA, isti za sve segmente
    # Posledica je bio SUDAR: dva dokumenta iz istog segmentiranog posla, u
    # istom predmetu, dobijala su identicne ID-eve i drugi je prepisao prvi.
    #
    # Umesto da se svaki pisac testira posebno, verzija se izvodi iz teksta koji
    # se STVARNO indeksira. Tako nijedan pisac ne moze da je pogresi, a
    # `source_sha256` ostaje ono sto i jeste -- podatak o izvornom fajlu.
    # Kanonska verzija se racuna JEDNOM, iz teksta dokumenta, i prosledjuje se
    # ovde izricitim parametrom. Namerno NIJE `manifest.source_sha256`: taj polje
    # su pisci punili razlicitim stvarima (hes bajtova fajla, hes bajtova CELOG
    # posla), sto je proizvelo sudar ID-eva medju segmentima jednog posla.
    #
    # Namerno se NE izvodi ni iz spojenih chunk-ova: `chunk_document` deli sa
    # preklapanjem (`OVERLAP_TOKENS = 100`), pa spajanje duplira tekst -- mereno
    # 31.600 znakova -> 36.428. Vrednost bi se tada razlikovala od one koju pisac
    # upisuje u `predmet_dokumenti.content_sha256`, i `prefiks_dokumenta` ne bi
    # nasao nijedan vektor dokumenta duzeg od jednog chunk-a. Tiho.
    #
    # Fail-closed po RULE 6: bez izricite verzije se NE upisuje nista.
    if not verzija_dokumenta_id:
        raise NedovoljanIdentitet(
            "verzija_dokumenta_id nije prosledjena — vektori se ne upisuju bez identiteta"
        )
    from shared.vector_identity import proveri_kanonsku_verziju as _proveri
    _verzija = _proveri(verzija_dokumenta_id)

    records = []
    for chunk, vec in zip(manifest.chunks, vectors_raw):
        text_stored = chunk.text[:_TEXT_TRUNCATE]
        metadata = {
            "session_id": session_id,
            "source_filename": manifest.source_filename,
            "source_format": manifest.source_format,
            "chunk_index": chunk.chunk_index,
            "chunk_mode": chunk.chunk_mode,
            "article_label": chunk.article_label or "",
            "text": text_stored,
            "token_count": chunk.token_count,
            "expires_at": exp_iso,
        }
        if extra_metadata:
            metadata.update(extra_metadata)
        # Identitet se dodaje POSLE `extra_metadata`, da ga pozivalac ne moze
        # slucajno pregaziti.
        metadata.update(metapodaci_identiteta(
            scope=_scope, verzija=_verzija, chunk_index=chunk.chunk_index,
            predmet_id=_predmet_id or None,
        ))
        records.append({
            "id": canonical_vector_id(_scope, _verzija, chunk.chunk_index),
            "values": vec,
            "metadata": metadata,
        })

    # Delimičan batch je stvarno stanje, ne teorija: ako padne 3. od 5 batch-eva,
    # prva dva su VEĆ u Pinecone-u. Izuzetak se namerno propušta gore (pozivalac
    # tada ne sme da tvrdi da je dokument indeksiran), ali se broj već upisanih
    # vektora zapisuje u log — bez toga se orphan vektori ne mogu ni prebrojati.
    BATCH_SIZE = 50
    _upisano = 0
    for i in range(0, len(records), BATCH_SIZE):
        _batch = records[i:i + BATCH_SIZE]
        try:
            index.upsert(vectors=_batch, namespace=namespace)
        except Exception:
            logger.error(
                "[INGEST] batch pao: session=%s ns=%s upisano_pre_pada=%d od %d — "
                "ti vektori OSTAJU u Pinecone-u",
                session_id, namespace, _upisano, len(records),
            )
            raise
        _upisano += len(_batch)
    logger.info(
        "[INGEST] session=%s ns=%s chunks=%d",
        session_id, namespace, _upisano,
    )
    return _upisano


# ─── Kanonska ocena ishoda ingesta ───────────────────────────────────────────
#
# BETA-DATA-CONFIDENTIALITY-004. Do ovog sprinta su obe pozivne putanje
# (`api.py` upload i `routers/smart_intake.py`) svaka za sebe zakljucivale da
# li je ingest uspeo, i obe su gresile na isti nacin: uspeh se izvodio iz
# ODSUSTVA izuzetka, a `count` koji ova funkcija vraca nije se proveravao
# nijednom. Ovde su te dve odluke imenovane i na jednom mestu, da bi mogle da
# se testiraju kao produkcijske funkcije umesto da ih test rekonstruise.


def ingest_je_potpun(upisano: int, ocekivano: int) -> bool:
    """Da li je dokument STVARNO cele duzine u indeksu.

    Fail-closed na svaku nepravilnost: negativan ili nulti ocekivani broj nije
    "trivijalno tacan" nego neispravan ulaz, i ne sme da proglasi uspeh.
    """
    if ocekivano <= 0:
        return False
    return upisano == ocekivano


# Poruke po kojima se prepoznaje da je Pinecone odbio upis zbog KVOTE. Kvota je
# jedino stanje u kome se dokument sme prihvatiti bez indeksiranja (korisnik
# nije kriv, i stanje je popravljivo ponavljanjem). Sve ostalo je greska.
#
# Raniji klasifikator je glasio `"storage" in str(exc).lower()` -- presiroko:
# svaka greska cija poruka sadrzi "storage", ukljucujuci greske Supabase
# Storage-a i poruke koje pominju `storage_path`, tiho je postajala "kvota", pa
# je dokument zavrsavao kao 'sacuvano' umesto da podigne gresku.
_KVOTA_POJMOVI = (
    "too many",
    "quota",
    "max serverless index storage",
    "storage size exceeded",
    "storage is full",
)


def je_kvota_greska(exc: BaseException) -> bool:
    """Da li je izuzetak Pinecone kvota, a ne stvarna greska."""
    poruka = str(exc)
    if "429" in poruka:
        return True
    return any(p in poruka.lower() for p in _KVOTA_POJMOVI)
