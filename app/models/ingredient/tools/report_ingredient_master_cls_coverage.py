"""
Per-class image coverage for ml_datasets/ingredient_master_cls vs model_label_to_master.json.

275-way training: every class key in the master JSON should have at least one image
in train/ (and ideally val/) before yolo classify train.

Usage:
  python report_ingredient_master_cls_coverage.py \\
    --master-json app/models/ingredient/data/model_label_to_master.json \\
    --dataset-root ml_datasets/ingredient_master_cls

  python report_ingredient_master_cls_coverage.py ... --min-train 1 --fail-on-gap
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SPLITS = ("train", "val", "test")

_TOOL_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _TOOL_DIR.parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.models.ingredient.tools.assemble_ingredient_master_cls_dataset import load_master_nn_to_ing


def count_images(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    n = 0
    for p in folder.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            n += 1
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="Report YOLO cls coverage vs ingredient_master map")
    parser.add_argument("--master-json", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--min-train", type=int, default=1, help="Minimum train images per class (default 1)")
    parser.add_argument(
        "--fail-on-gap",
        action="store_true",
        help="Exit 1 if any class is below --min-train in train split",
    )
    args = parser.parse_args()

    if not args.master_json.exists():
        print(f"ERROR: missing {args.master_json}", file=sys.stderr)
        sys.exit(2)

    data = json.loads(args.master_json.read_text(encoding="utf-8"))
    labels = data.get("labels") or {}
    nn_to_ing = load_master_nn_to_ing(args.master_json)
    # assemble 스크립트와 동일: 디스크 폴더명 = JSON 라벨 키(예: apple 또는 ing_00042)
    class_folders = sorted(set(nn_to_ing.values()))
    root = args.dataset_root

    per_class: List[Tuple[str, str, int, int, int]] = []
    gap_train: List[str] = []

    def meta_for_folder(folder: str) -> Dict[str, Any]:
        for lk, mv in labels.items():
            if str(lk) == folder and isinstance(mv, dict):
                return mv
        return {}

    for folder in class_folders:
        meta = meta_for_folder(folder)
        nn = str(meta.get("normalizedName") or meta.get("normalized_name") or "")
        tr = count_images(root / "train" / folder)
        va = count_images(root / "val" / folder)
        te = count_images(root / "test" / folder)
        per_class.append((folder, nn, tr, va, te))
        if tr < args.min_train:
            gap_train.append(folder)

    summary = {
        "masterClasses": len(class_folders),
        "normalizedNamesInMap": len(nn_to_ing),
        "datasetRoot": str(root.resolve()),
        "perSplitTotals": {
            "train": sum(x[2] for x in per_class),
            "val": sum(x[3] for x in per_class),
            "test": sum(x[4] for x in per_class),
        },
        "classesWithTrainImages": sum(1 for x in per_class if x[2] > 0),
        "classesBelowMinTrain": len(gap_train),
        "missingTrainClasses": gap_train,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print()
    print(
        f"요약: 마스터 {len(class_folders)} 클래스 중 "
        f"train에 사진이 있는 클래스 {summary['classesWithTrainImages']}개, "
        f"train이 {args.min_train}장 미만인 클래스 {len(gap_train)}개."
    )
    if gap_train and len(gap_train) <= 40:
        print("부족 클래스:", ", ".join(gap_train))
    elif gap_train:
        print(f"부족 클래스(처음 20개): {', '.join(gap_train[:20])} …")

    if args.fail_on_gap and gap_train:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
