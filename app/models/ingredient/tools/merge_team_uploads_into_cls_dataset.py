"""
Copy team_uploads/{train,val,test}/ing_XXX/* into ml_datasets/ingredient_master_cls with
the same per-split cap as fetch_ingredient_images_web: each of train/val/test under an
ing_* class holds at most --max-per-class images; fill train first, then val, then test.
Skips copying when all three splits are full. Does not delete or trim source or dest.

Usage (backend_2 root):
  python app/models/ingredient/tools/merge_team_uploads_into_cls_dataset.py
  python app/models/ingredient/tools/merge_team_uploads_into_cls_dataset.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set

_TOOL_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _TOOL_DIR.parents[3]

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_SPLIT_ORDER = ("train", "val", "test")


def count_images(dir_path: Path) -> int:
    if not dir_path.is_dir():
        return 0
    n = 0
    for p in dir_path.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXT:
            n += 1
    return n


def list_images_sorted(d: Path) -> List[Path]:
    if not d.is_dir():
        return []
    files = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT]
    return sorted(files, key=lambda x: x.name.lower())


def names_in_dir(d: Path) -> Set[str]:
    if not d.is_dir():
        return set()
    return {p.name for p in d.iterdir() if p.is_file()}


def safe_dst_name(parent: Path, base: str, used: Set[str]) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    if base not in used:
        used.add(base)
        return parent / base
    stem = Path(base).stem
    suf = Path(base).suffix
    i = 1
    while f"{stem}_{i}{suf}" in used:
        i += 1
    name = f"{stem}_{i}{suf}"
    used.add(name)
    return parent / name


def split_live_counts(dest_root: Path, folder: str) -> Dict[str, int]:
    return {s: count_images(dest_root / s / folder) for s in _SPLIT_ORDER}


def next_split(live: Dict[str, int], cap: int) -> Optional[str]:
    for s in _SPLIT_ORDER:
        if live[s] < cap:
            return s
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge team_uploads into ingredient_master_cls with split caps")
    parser.add_argument(
        "--team-root",
        type=Path,
        default=_BACKEND_ROOT / "data_sources" / "team_uploads",
    )
    parser.add_argument(
        "--dest-root",
        type=Path,
        default=_BACKEND_ROOT / "ml_datasets" / "ingredient_master_cls",
    )
    parser.add_argument("--max-per-class", type=int, default=100, help="cap per split folder ing_*")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cap = args.max_per_class
    if cap < 1:
        raise SystemExit("--max-per-class must be >= 1")

    team = args.team_root
    dest = args.dest_root
    if not team.is_dir():
        raise SystemExit(f"Missing --team-root: {team}")

    stats = {
        "copied": 0,
        "skipped_no_room": 0,
        "source_folders": 0,
        "by_split": {"train": 0, "val": 0, "test": 0},
    }

    for src_split in _SPLIT_ORDER:
        split_root = team / src_split
        if not split_root.is_dir():
            continue
        for ing_dir in sorted(split_root.iterdir()):
            if not ing_dir.is_dir() or not ing_dir.name.startswith("ing_"):
                continue
            folder = ing_dir.name
            stats["source_folders"] += 1
            live = split_live_counts(dest, folder)
            used_per_split: Dict[str, Set[str]] = {s: set(names_in_dir(dest / s / folder)) for s in _SPLIT_ORDER}

            for src in list_images_sorted(ing_dir):
                sp = next_split(live, cap)
                if sp is None:
                    stats["skipped_no_room"] += 1
                    continue
                dest_dir = dest / sp / folder
                base = f"team__{src.name}"
                if args.dry_run:
                    live[sp] += 1
                    stats["copied"] += 1
                    stats["by_split"][sp] += 1
                    continue
                dst_path = safe_dst_name(dest_dir, base, used_per_split[sp])
                shutil.copy2(src, dst_path)
                live[sp] += 1
                stats["copied"] += 1
                stats["by_split"][sp] += 1

    print(json.dumps({"team_root": str(team), "dest_root": str(dest), "dry_run": args.dry_run, **stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
