"""
Export CSV checklist for YOLO cls data collection: which ing_XXXXX still need train images.

Usage:
  python export_ingredient_cls_gap_checklist.py \\
    --master-json app/models/ingredient/data/model_label_to_master.json \\
    --dataset-root ml_datasets/ingredient_master_cls \\
    --out app/models/ingredient/data/ingredient_cls_gap_checklist.csv

  # full 275 rows (for spreadsheet filtering)
  python export_ingredient_cls_gap_checklist.py ... --all-rows
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

_TOOL_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _TOOL_DIR.parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.models.ingredient.tools.assemble_ingredient_master_cls_dataset import load_master_nn_to_ing

_ING_RE = re.compile(r"^ing_(\d+)$", re.IGNORECASE)


def count_images(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    n = 0
    for p in folder.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            n += 1
    return n


def parse_ingredient_id(key: str) -> Optional[int]:
    m = _ING_RE.match(str(key).strip())
    if not m:
        return None
    return int(m.group(1), 10)


def main() -> None:
    here = Path(__file__).resolve().parent
    default_out = here.parent / "data" / "ingredient_cls_gap_checklist.csv"

    parser = argparse.ArgumentParser(description="Export gap CSV for ingredient cls training data")
    parser.add_argument("--master-json", type=Path, default=here.parent / "data" / "model_label_to_master.json")
    parser.add_argument("--dataset-root", type=Path, default=Path("ml_datasets/ingredient_master_cls"))
    parser.add_argument("--min-train", type=int, default=1)
    parser.add_argument(
        "--all-rows",
        action="store_true",
        help="write all 275 classes; default is only classes below --min-train in train",
    )
    parser.add_argument("--out", type=Path, default=default_out)
    args = parser.parse_args()

    if not args.master_json.exists():
        print(f"ERROR: {args.master_json} not found", file=sys.stderr)
        sys.exit(2)

    data = json.loads(args.master_json.read_text(encoding="utf-8"))
    labels: Dict[str, Any] = data.get("labels") or {}
    nn_to_ing = load_master_nn_to_ing(args.master_json)
    class_folders = sorted(set(nn_to_ing.values()))
    root = args.dataset_root

    rows: List[Dict[str, Any]] = []

    for folder in class_folders:
        meta: Dict[str, Any] = {}
        for lk, mv in labels.items():
            if str(lk) == folder and isinstance(mv, dict):
                meta = mv
                break
        nn = str(meta.get("normalizedName") or meta.get("normalized_name") or "")
        display = str(meta.get("displayName") or meta.get("display_name") or nn)
        cat = str(meta.get("categorySuggestion") or meta.get("category_suggestion") or "")

        tr = count_images(root / "train" / folder)
        va = count_images(root / "val" / folder)
        te = count_images(root / "test" / folder)
        needs = "Y" if tr < args.min_train else "N"
        if not args.all_rows and tr >= args.min_train:
            continue
        iid = parse_ingredient_id(folder)
        rows.append(
            {
                "model_folder": folder,
                "ingredient_id": iid if iid is not None else "",
                "normalized_name": nn,
                "display_name": display,
                "category_suggestion": cat,
                "train_count": tr,
                "val_count": va,
                "test_count": te,
                "needs_train_images": needs,
                "team_upload_path": f"data_sources/team_uploads/train/{folder}/",
            }
        )

    # stable sort: gap first (Y) then by ingredient_id
    def sort_key(r: Dict[str, Any]) -> Tuple[int, int]:
        y = 0 if r["needs_train_images"] == "Y" else 1
        iid = r["ingredient_id"]
        if iid == "":
            return (y, 999999)
        return (y, int(iid))

    rows.sort(key=sort_key)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "model_folder",
        "ingredient_id",
        "normalized_name",
        "display_name",
        "category_suggestion",
        "train_count",
        "val_count",
        "test_count",
        "needs_train_images",
        "team_upload_path",
    ]
    with args.out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(
        json.dumps(
            {
                "out": str(args.out.resolve()),
                "rowsWritten": len(rows),
                "onlyGaps": not args.all_rows,
                "minTrain": args.min_train,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
