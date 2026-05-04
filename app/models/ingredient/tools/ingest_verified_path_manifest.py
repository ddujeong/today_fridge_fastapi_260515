"""
Copy labeled images into ml_datasets/... using an explicit CSV manifest.

Each row binds ONE normalized_name (must exist in model_label_to_master.json) to ONE
directory tree whose photos have been human-verified as that ingredient.

CSV columns (utf-8):
  normalized_name, source_dir

Paths may be absolute or relative to current working directory.

Usage:
  python ingest_verified_path_manifest.py \\
    --manifest app/models/ingredient/data/verified_path_manifest.csv \\
    --master-json app/models/ingredient/data/model_label_to_master.json \\
    --out ml_datasets/ingredient_master_cls \\
    --mode copy
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, Set, Tuple

_TOOL_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _TOOL_DIR.parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.models.ingredient.tools.assemble_ingredient_master_cls_dataset import (  # noqa: E402
    IMAGE_EXTENSIONS,
    iter_images,
    safe_copy,
)


def load_nn_to_ing(master_path: Path) -> Dict[str, str]:
    data = json.loads(master_path.read_text(encoding="utf-8"))
    labels = data.get("labels") or {}
    out: Dict[str, str] = {}
    for ing_key, meta in labels.items():
        if not isinstance(meta, dict):
            continue
        nn = meta.get("normalizedName") or meta.get("normalized_name")
        if nn:
            out[str(nn)] = str(ing_key)
    return out


def main() -> None:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Ingest CSV manifest of verified label→directory pairs")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--master-json", type=Path, default=here.parent / "data" / "model_label_to_master.json")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=["copy", "symlink"], default="copy")
    args = parser.parse_args()

    if not args.master_json.exists():
        raise SystemExit(f"missing --master-json: {args.master_json}")
    nn_to_ing = load_nn_to_ing(args.master_json)

    written: Set[Tuple[str, str]] = set()
    stats: Dict[str, int] = {}

    rows = 0
    with args.manifest.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        need = {"normalized_name", "source_dir"}
        if not reader.fieldnames or not need.issubset({x.strip() for x in reader.fieldnames}):
            raise SystemExit(f"CSV must have columns: {sorted(need)}, got {reader.fieldnames}")
        for row in reader:
            nn = (row.get("normalized_name") or "").strip()
            src_raw = (row.get("source_dir") or "").strip()
            if not nn or not src_raw:
                continue
            rows += 1
            ing_key = nn_to_ing.get(nn)
            if not ing_key:
                raise SystemExit(f"normalized_name not in master JSON: {nn!r}")
            src = Path(src_raw)
            if not src.is_dir():
                raise SystemExit(f"source_dir is not a directory: {src}")
            n = 0
            for img in iter_images(src):
                dst = args.out / "train" / ing_key / f"manifest_{nn[:16]}__{img.name}"
                safe_copy(img, dst, args.mode, written)
                n += 1
            stats[nn] = n

    print(json.dumps({"manifestRows": rows, "perNormalizedName": stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
