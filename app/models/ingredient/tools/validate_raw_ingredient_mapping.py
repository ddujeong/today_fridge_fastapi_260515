"""
Validate model_label_to_master.json against ingredient_normalized_vocab.json.

Ensures every normalizedName in the YOLO label map exists in the DB vocabulary
(from the latest COPY sync extract).

Exit code 0 if OK, 1 if any label maps to a name missing from vocab.

Usage:
  python validate_raw_ingredient_mapping.py \\
    --vocab ../data/ingredient_normalized_vocab.json \\
    --map ../data/model_label_to_master.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Set


def load_vocab_names(vocab_path: Path) -> Set[str]:
    data = json.loads(vocab_path.read_text(encoding="utf-8"))
    names = data.get("names")
    if not isinstance(names, list):
        raise ValueError("vocab JSON must contain 'names' array")
    return set(str(x) for x in names)


def load_label_map(map_path: Path) -> Dict[str, Dict[str, Any]]:
    data = json.loads(map_path.read_text(encoding="utf-8"))
    labels = data.get("labels")
    if not isinstance(labels, dict):
        raise ValueError("map JSON must contain 'labels' object")
    return labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vocab", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    args = parser.parse_args()

    vocab = load_vocab_names(args.vocab)
    labels = load_label_map(args.map)
    missing: list[tuple[str, str]] = []

    for model_key, meta in sorted(labels.items()):
        nn = meta.get("normalizedName") or meta.get("normalized_name")
        if not nn:
            missing.append((model_key, "<no normalizedName>"))
            continue
        if str(nn) not in vocab:
            missing.append((model_key, str(nn)))

    if missing:
        print("Invalid mappings (normalizedName not in vocab):", file=sys.stderr)
        for k, v in missing:
            print(f"  {k!r} -> {v!r}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: {len(labels)} model labels all resolve to names present in vocab ({len(vocab)} distinct).")


if __name__ == "__main__":
    main()
