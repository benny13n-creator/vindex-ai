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
            # Namespace has stat entry but no vectors — clean it up
            if not dry_run:
                index.delete(delete_all=True, namespace=ns)
                logger.info("[CLEANUP] Deleted empty namespace %s", ns)
            namespaces_deleted += 1
            continue

        expires_at = matches[0].get("metadata", {}).get("expires_at", "")
        if not expires_at or is_expired(expires_at):
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
