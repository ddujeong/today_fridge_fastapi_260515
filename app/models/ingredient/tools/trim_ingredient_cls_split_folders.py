"""
Cap each ing_* folder under a YOLO cls dataset split so image count <= --max-per-class.

Keeps the first N files in lexicographic path order (stable, reproducible); deletes the rest.
Use after assemble or heavy web fetch when some classes exceed the training budget.

  python trim_ingredient_cls_split_folders.py --dataset-root ml_datasets/ingredient_master_cls
  python trim_ingredient_cls_split_folders.py --dataset-root ml_datasets/ingredient_master_cls --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
DEFAULT_SPLITS = ("train", "val", "test")


def list_images(class_dir: Path) -> List[Path]:
    if not class_dir.is_dir():
        return []
    out: List[Path] = []
    for p in class_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXT:
            out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trim ing_* class folders so each has at most --max-per-class images per split"
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        required=True,
        help="e.g. ml_datasets/ingredient_master_cls",
    )
    parser.add_argument(
        "--max-per-class",
        type=int,
        default=1000,
        help="maximum images kept per ing_* folder in each split (default 1000)",
    )
    parser.add_argument(
        "--splits",
        default="train,val,test",
        help="comma-separated split directory names under dataset-root",
    )
    parser.add_argument("--dry-run", action="store_true", help="print actions only, do not delete")
    args = parser.parse_args()

    if args.max_per_class < 1:
        print("--max-per-class must be >= 1", file=sys.stderr)
        sys.exit(2)

    root = args.dataset_root
    if not root.is_dir():
        print(f"Missing dataset root: {root}", file=sys.stderr)
        sys.exit(2)

    splits = tuple(s.strip() for s in args.splits.split(",") if s.strip())
    if not splits:
        splits = DEFAULT_SPLITS

    summary: dict = {"removed": 0, "folders_trimmed": 0, "splits": {}}

    for sp in splits:
        split_root = root / sp
        if not split_root.is_dir():
            continue
        split_removed = 0
        split_trimmed = 0
        for ing_dir in sorted(split_root.iterdir()):
            if not ing_dir.is_dir():
                continue
            if not ing_dir.name.startswith("ing_"):
                continue
            files = list_images(ing_dir)
            over = len(files) - args.max_per_class
            if over <= 0:
                continue
            split_trimmed += 1
            victims = files[args.max_per_class :]
            for p in victims:
                if args.dry_run:
                    split_removed += 1
                else:
                    try:
                        p.unlink()
                        split_removed += 1
                    except OSError as exc:
                        print(json.dumps({"err": str(exc), "path": str(p)}, ensure_ascii=False))
        summary["splits"][sp] = {"trimmed_folders": split_trimmed, "files_removed": split_removed}
        summary["folders_trimmed"] += split_trimmed
        summary["removed"] += split_removed

    print(json.dumps({"dry_run": args.dry_run, "max_per_class": args.max_per_class, **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
