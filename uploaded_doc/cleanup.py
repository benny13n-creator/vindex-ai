"""Cleanup expired tmp_* Pinecone namespaces."""

from __future__ import annotations

import logging
import os

from .session import is_expired

logger = logging.getLogger(__name__)

_TMP_NS_PREFIX = "tmp_"


def _get_pinecone_index():
    from pinecone import Pinecone
    api_key = os.environ["PINECONE_API_KEY"]
    host = os.environ.get("PINECONE_HOST", "")
    pc = Pinecone(api_key=api_key)
    if host:
        return pc.Index(host=host)
    indexes = pc.list_indexes()
    index_name = indexes[0].name
    return pc.Index(index_name)


def cleanup_expired(dry_run: bool = False) -> dict:
    """Delete all expired tmp_* namespaces from Pinecone.

    Returns summary dict with namespaces_deleted, chunks_deleted,
    namespaces_inspected counts.
    """
    index = _get_pinecone_index()

    stats = index.describe_index_stats()
    all_namespaces = stats.get("namespaces", {})

    tmp_namespaces = {
        ns: info
        for ns, info in all_namespaces.items()
        if ns.startswith(_TMP_NS_PREFIX)
    }

    namespaces_inspected = len(tmp_namespaces)
    namespaces_deleted = 0
    chunks_deleted = 0

    for ns, info in tmp_namespaces.items():
        # Fetch one chunk to read its expires_at metadata
        result = index.query(
            vector=[0.0] * 3072,
            top_k=1,
            namespace=ns,
            include_metadata=True,
        )
        matches = result.get("matches", [])
        if not matches:
            # NIGHT-004 (2026-08-09): this used to be `index.delete(delete_all=True)`
            # on the theory that "stat entry but no vectors = junk". Pinecone
            # serverless is EVENTUALLY CONSISTENT: query and describe_index_stats
            # do not converge at the same instant, so a namespace written seconds
            # ago legitimately answers an empty query while its vectors exist.
            #
            # That would be tolerable in a nightly job. It is not tolerable here:
            # routers/dokument.py and api.py both fire cleanup_expired() as a
            # background task on EVERY upload, so one lawyer's upload could
            # destroy another lawyer's document that had just been indexed — the
            # owner's next question about it returning "session not found", 24h
            # early, with no error on their side.
            #
            # An empty namespace costs nothing to leave alone. Count it, skip it.
            logger.info("[CLEANUP] Namespace %s returned no vectors — preskačem "
                        "(prazan upit nije dokaz da je namespace prazan).", ns)
            continue

        expires_at = matches[0].get("metadata", {}).get("expires_at", "")
        if not expires_at:
            # NIGHT-004: missing metadata is UNKNOWN, not EXPIRED. Deleting on a
            # blank expires_at meant any vector written by a path that does not
            # set that field took its whole namespace down with it.
            logger.warning("[CLEANUP] Namespace %s nema expires_at metapodatak — "
                           "ne brišem (nepoznato != isteklo).", ns)
            continue

        if is_expired(expires_at):
            vector_count = info.get("vector_count", 0)
            chunks_deleted += vector_count
            namespaces_deleted += 1
            if not dry_run:
                index.delete(delete_all=True, namespace=ns)
                logger.info(
                    "[CLEANUP] Deleted expired namespace %s (%d vectors)",
                    ns, vector_count,
                )
            else:
                logger.info(
                    "[CLEANUP] dry_run: would delete %s (%d vectors, expires=%s)",
                    ns, vector_count, expires_at,
                )

    return {
        "namespaces_deleted": namespaces_deleted,
        "chunks_deleted": chunks_deleted,
        "namespaces_inspected": namespaces_inspected,
    }


def main() -> None:
    import sys
    import json

    sys.stdout.reconfigure(encoding="utf-8")
    dry_run = "--dry-run" in sys.argv
    result = cleanup_expired(dry_run=dry_run)
    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"[CLEANUP {mode}] {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    main()
