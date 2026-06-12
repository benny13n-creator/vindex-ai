# -*- coding: utf-8 -*-
"""
Phase 1.1b — Re-chunk expanded VKS corpus (200 → 867 decisions).
Calls chunk_corpus() on all raw decisions, writes chunked_manifest.json.
READ-WRITE to data/sudska_praksa/ only.
"""
import sys, json, logging
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("chunk_expand")

sys.path.insert(0, str(Path(__file__).parent))
from chunker_case_law import chunk_corpus

BASE = Path(__file__).parent / "data" / "sudska_praksa"
RAW_DIR = BASE / "raw"
CHUNKED_DIR = BASE / "chunked"

log.info("=== Phase 1.1b: Chunk expanded corpus ===")
log.info("Raw dir  : %s", RAW_DIR)
log.info("Chunk dir: %s", CHUNKED_DIR)

# Count input
for slug in ["krivicna","gradjanska","upravna","zastitaprava"]:
    n = len(list((RAW_DIR / slug).glob("*.json")))
    log.info("  %s: %d raw decisions", slug, n)

stats = chunk_corpus(RAW_DIR, CHUNKED_DIR)

log.info("=== Chunking complete ===")
log.info("Total decisions : %d", stats["total_decisions"])
log.info("Total chunks    : %d", stats["total_chunks"])
log.info("Errors          : %d", stats["errors"])
for slug, m in stats["by_matter"].items():
    log.info("  %s: %d decisions → %d chunks (avg %.2f)", slug, m["decisions"], m["chunks"], m["avg"])

# Write updated chunked_manifest.json
manifest = {
    "phase": "1.1b",
    "chunked_at": datetime.now(timezone.utc).isoformat(),
    "chunker_version": "1.0",
    "branch": "main",
    "source_dataset": "data/sudska_praksa/raw/ (Phase 1.0b expansion, 867 decisions)",
    "target_namespace_for_phase_1_2": "sudska_praksa",
    "totals": {
        "decisions_processed": stats["total_decisions"],
        "decisions_with_errors": stats["errors"],
        "total_chunks": stats["total_chunks"],
        "avg_chunks_per_decision": round(stats["total_chunks"] / stats["total_decisions"], 2)
            if stats["total_decisions"] else 0,
    },
    "by_matter": stats["by_matter"],
}
(BASE / "chunked_manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
)
log.info("chunked_manifest.json written.")

if stats["errors"] > 0:
    log.warning("Errors logged to data/sudska_praksa/chunked_errors.txt")
    sys.exit(1)
sys.exit(0)
