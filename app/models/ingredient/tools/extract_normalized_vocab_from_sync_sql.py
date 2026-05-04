"""
Extract DISTINCT normalized_name (+ counts) from ingredient_master COPY dump.

Reads team sync SQL (same shape as export_ingredient_master_sync_sql.py output):
  COPY ... (ingredient_id, category_id, canonical_name, normalized_name, ...) FROM stdin;
  <tab-separated data rows>
  \\.

Usage:
  python extract_normalized_vocab_from_sync_sql.py \\
    --sql ../../../../db_scripts/ingredient_master_normalize/sync_ingredient_master.sql \\
    --out ../data/ingredient_normalized_vocab.json

Re-run whenever a new COPY sync script is delivered.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List


def iter_copy_data_lines(sql_path: Path) -> Iterator[str]:
    text = sql_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_copy = False
    for line in lines:
        if not in_copy:
            if line.startswith("COPY ") and "FROM stdin" in line and "ingredient_master" in line:
                in_copy = True
            continue
        stripped = line.strip()
        if stripped == r"\.":  # COPY end marker
            break
        if stripped and not stripped.startswith("--"):
            yield line.rstrip("\n")


def parse_normalized_names(lines: Iterator[str]) -> List[str]:
    """Assumes tab-separated COPY rows with exactly 12 columns (no tabs inside fields)."""
    names: List[str] = []
    bad = 0
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 12:
            bad += 1
            continue
        nn = parts[3].strip()
        if nn and nn != r"\N":
            names.append(nn)
    if bad:
        print(f"[warn] skipped {bad} rows (expected 12 tab-separated columns)")
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ingredient normalized_name vocabulary JSON from sync SQL")
    parser.add_argument("--sql", type=Path, required=True, help="Path to sync_ingredient_master.sql")
    parser.add_argument("--out", type=Path, required=True, help="Output JSON path")
    args = parser.parse_args()

    names = parse_normalized_names(iter_copy_data_lines(args.sql))
    counts = Counter(names)
    distinct = sorted(counts.keys())

    payload = {
        "schema": "ingredient_normalized_vocab_v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceSql": str(args.sql.resolve()),
        "rowCountInCopy": len(names),
        "distinctCount": len(distinct),
        "names": distinct,
        "counts": dict(sorted(counts.items(), key=lambda x: x[0])),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(distinct)} distinct normalized_name)")


if __name__ == "__main__":
    main()
