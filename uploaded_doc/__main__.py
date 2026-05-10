"""CLI: python -m uploaded_doc <path-to-file>"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m uploaded_doc <path-to-file>", file=sys.stderr)
        sys.exit(1)

    from uploaded_doc.chunker import chunk_document
    from uploaded_doc.extractor import extract

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    text, is_scanned = extract(path)
    fmt = path.suffix.lstrip(".").lower()
    if fmt not in ("pdf", "docx", "txt"):
        fmt = "txt"

    source_meta = {
        "source_filename": path.name,
        "source_format": fmt,
        "source_sha256": _sha256(path),
        "is_scanned": is_scanned,
        "session_id": "__local__",
    }

    manifest = chunk_document(text, source_meta)

    # Write manifest file
    manifests_dir = Path(__file__).parent.parent / "manifests"
    manifests_dir.mkdir(exist_ok=True)
    out_path = manifests_dir / f"{path.stem}-manifest.json"
    out_path.write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    # Print summary
    print(f"\n{'='*60}")
    print(f"File:       {manifest.source_filename}")
    print(f"Format:     {manifest.source_format}")
    print(f"SHA256:     {manifest.source_sha256[:16]}...")
    print(f"Scanned:    {manifest.is_scanned}")
    print(f"Mode:       {manifest.chunk_mode_used}")
    print(f"Chunks:     {manifest.total_chunks}")
    print(f"Articles:   {len(manifest.article_labels_detected)} labels detected")
    if manifest.article_labels_detected:
        print(f"  Labels:   {manifest.article_labels_detected[:5]}")
    print(f"Tokens:     p10={manifest.token_p10}  p50={manifest.token_p50}  p90={manifest.token_p90}")
    print(f"Manifest:   {out_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
