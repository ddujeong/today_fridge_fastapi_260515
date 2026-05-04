"""
Assemble YOLO classification dataset under ml_datasets/ingredient_master_cls/

Recommended combo:
  1) GroceryStoreDataset Fruit/Vegetables (coarse folder → Korean normalized_name)
  2) Optional Fruits-360 (folder name → normalized_name, map JSON filled by team)
  3) Optional team_uploads/train/ing_XXXXX/ already keyed by master id

Requires model_label_to_master.json from export_yolo_label_assets_from_db.py (ing_XXXXX keys).

Usage:
  python assemble_ingredient_master_cls_dataset.py \\
    --master-json ../data/model_label_to_master.json \\
    --grocery-root ../../data_sources/GroceryStoreDataset/dataset \\
    --out ../../ml_datasets/ingredient_master_cls \\
    --mode copy

  python assemble_ingredient_master_cls_dataset.py \\
    --master-json ../data/model_label_to_master.json \\
    --fruits360-root ../../data_sources/Fruits-360/Training \\
    --fruits360-map ../data/fruits360_folder_to_normalized_name.json \\
    --out ../../ml_datasets/ingredient_master_cls \\
    --mode copy

  python assemble_ingredient_master_cls_dataset.py \\
    --master-json ../data/model_label_to_master.json \\
    --team-root ../../data_sources/team_uploads \\
    --out ../../ml_datasets/ingredient_master_cls
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, Iterator, Set, Tuple

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SPLITS = ("train", "val", "test")
RAW_GROUPS = ("Fruit", "Vegetables")


def load_master_nn_to_ing(master_path: Path) -> Dict[str, str]:
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


def load_grocery_map(path: Path) -> Dict[str, Dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    fruit = data.get("Fruit") or {}
    veg = data.get("Vegetables") or {}
    if not isinstance(fruit, dict):
        fruit = {}
    if not isinstance(veg, dict):
        veg = {}
    return {"Fruit": {str(k): str(v) for k, v in fruit.items()}, "Vegetables": {str(k): str(v) for k, v in veg.items()}}


def load_fruits360_map(path: Path) -> Dict[str, str]:
    exact, _prefix = load_fruits360_maps(path)
    return exact


def load_fruits360_maps(path: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Exact folder name → normalized_name, plus optional longest-prefix map (English phrase → KR)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    m = data.get("map") or {}
    if not isinstance(m, dict):
        m = {}
    exact = {str(k): str(v) for k, v in m.items()}
    p = data.get("prefixMap") or {}
    if not isinstance(p, dict):
        p = {}
    prefix = {str(k): str(v) for k, v in p.items()}
    return exact, prefix


def resolve_f360_normalized(folder_name: str, exact: Dict[str, str], prefix: Dict[str, str]) -> str | None:
    if folder_name in exact:
        return exact[folder_name]
    best_nn: str | None = None
    best_len = -1
    for pref, nn in prefix.items():
        if folder_name == pref or folder_name.startswith(pref + " "):
            if len(pref) > best_len:
                best_len = len(pref)
                best_nn = nn
    return best_nn


def iter_images(root: Path) -> Iterator[Path]:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            yield p


def safe_copy(src: Path, dst: Path, mode: str, written: Set[Tuple[str, str]]) -> None:
    """Avoid duplicate dst basename collisions across sources."""
    key = (str(dst.parent), dst.name)
    if key in written:
        stem, suf = dst.stem, dst.suffix
        i = 1
        while (str(dst.parent), f"{stem}_{i}{suf}") in written:
            i += 1
        dst = dst.parent / f"{stem}_{i}{suf}"
        key = (str(dst.parent), dst.name)
    written.add(key)

    dst.parent.mkdir(parents=True, exist_ok=True)
    if mode == "copy":
        shutil.copy2(src, dst)
    elif mode == "symlink":
        if dst.exists():
            return
        dst.symlink_to(src.resolve())
    else:
        raise ValueError(f"unknown mode: {mode}")


def ingest_grocery(
    *,
    grocery_root: Path,
    out_root: Path,
    grocery_map: Dict[str, Dict[str, str]],
    nn_to_ing: Dict[str, str],
    mode: str,
    written: Set[Tuple[str, str]],
    stats: Dict[str, int],
) -> None:
    for split in SPLITS:
        for group in RAW_GROUPS:
            group_root = grocery_root / split / group
            if not group_root.is_dir():
                continue
            coarse_map = grocery_map.get(group, {})
            for coarse_dir in sorted(group_root.iterdir()):
                if not coarse_dir.is_dir():
                    continue
                coarse_name = coarse_dir.name
                nn = coarse_map.get(coarse_name)
                if not nn:
                    continue
                ing_key = nn_to_ing.get(nn)
                if not ing_key:
                    stats["grocery_skipped_no_master"] = stats.get("grocery_skipped_no_master", 0) + 1
                    continue
                n = 0
                for img in iter_images(coarse_dir):
                    dst = out_root / split / ing_key / f"grocery_{coarse_name}__{img.name}"
                    safe_copy(img, dst, mode, written)
                    n += 1
                stats["grocery_images"] = stats.get("grocery_images", 0) + n


def ingest_fruits360(
    *,
    training_root: Path,
    out_root: Path,
    folder_map: Dict[str, str],
    folder_prefix_map: Dict[str, str],
    nn_to_ing: Dict[str, str],
    mode: str,
    written: Set[Tuple[str, str]],
    stats: Dict[str, int],
) -> None:
    """Fruits-360: one folder per class under Training/. Split all into train (caller may move val later)."""
    if not training_root.is_dir():
        return
    target_split = "train"
    for folder in sorted(training_root.iterdir()):
        if not folder.is_dir():
            continue
        fname = folder.name
        nn = resolve_f360_normalized(fname, folder_map, folder_prefix_map)
        if not nn:
            stats["f360_skipped_unmapped"] = stats.get("f360_skipped_unmapped", 0) + 1
            continue
        ing_key = nn_to_ing.get(nn)
        if not ing_key:
            stats["f360_skipped_no_master"] = stats.get("f360_skipped_no_master", 0) + 1
            continue
        n = 0
        for img in iter_images(folder):
            dst = out_root / target_split / ing_key / f"f360_{fname.replace(' ', '_')}__{img.name}"
            safe_copy(img, dst, mode, written)
            n += 1
        stats["f360_images"] = stats.get("f360_images", 0) + n


def ingest_team(
    *,
    team_root: Path,
    out_root: Path,
    mode: str,
    written: Set[Tuple[str, str]],
    stats: Dict[str, int],
) -> None:
    """
    Expect team_root/train/ing_XXXXX/* or team_root/val/ing_XXXXX/*.
    If team_root already contains train/, merge those splits.
    """
    if not team_root.is_dir():
        return
    for split in SPLITS:
        split_root = team_root / split
        if not split_root.is_dir():
            continue
        for ing_dir in sorted(split_root.iterdir()):
            if not ing_dir.is_dir():
                continue
            name = ing_dir.name
            if not name.startswith("ing_"):
                continue
            n = 0
            for img in iter_images(ing_dir):
                dst = out_root / split / name / f"team__{img.name}"
                safe_copy(img, dst, mode, written)
                n += 1
            stats["team_images"] = stats.get("team_images", 0) + n


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble ingredient_master_cls YOLO dataset")
    here = Path(__file__).resolve().parent
    default_master = here.parent / "data" / "model_label_to_master.json"
    default_grocery_map = here.parent / "data" / "grocery_coarse_folder_to_normalized_name.json"
    default_f360_map = here.parent / "data" / "fruits360_folder_to_normalized_name.json"

    parser.add_argument("--master-json", type=Path, default=default_master)
    parser.add_argument("--grocery-map", type=Path, default=default_grocery_map)
    parser.add_argument("--grocery-root", type=Path, default=None, help=".../GroceryStoreDataset/dataset")
    parser.add_argument("--fruits360-root", type=Path, default=None, help=".../Fruits-360/Training")
    parser.add_argument("--fruits360-map", type=Path, default=default_f360_map)
    parser.add_argument("--team-root", type=Path, default=None, help=".../team_uploads")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=["copy", "symlink"], default="copy")
    args = parser.parse_args()

    if not args.master_json.exists():
        raise SystemExit(f"missing --master-json: {args.master_json}")

    nn_to_ing = load_master_nn_to_ing(args.master_json)
    written: Set[Tuple[str, str]] = set()
    stats: Dict[str, int] = {}

    args.out.mkdir(parents=True, exist_ok=True)

    grocery_map = load_grocery_map(args.grocery_map) if args.grocery_map.exists() else {"Fruit": {}, "Vegetables": {}}

    if args.grocery_root and args.grocery_root.is_dir():
        ingest_grocery(
            grocery_root=args.grocery_root,
            out_root=args.out,
            grocery_map=grocery_map,
            nn_to_ing=nn_to_ing,
            mode=args.mode,
            written=written,
            stats=stats,
        )
    elif args.grocery_root:
        print(f"[warn] --grocery-root not found, skip: {args.grocery_root}")

    if args.fruits360_root and args.fruits360_root.is_dir():
        fmap, fpref = load_fruits360_maps(args.fruits360_map) if args.fruits360_map.exists() else ({}, {})
        if not fmap and not fpref:
            print(f"[warn] fruits360 map empty or missing: {args.fruits360_map}")
        ingest_fruits360(
            training_root=args.fruits360_root,
            out_root=args.out,
            folder_map=fmap,
            folder_prefix_map=fpref,
            nn_to_ing=nn_to_ing,
            mode=args.mode,
            written=written,
            stats=stats,
        )
    elif args.fruits360_root:
        print(f"[warn] --fruits360-root not found, skip: {args.fruits360_root}")

    if args.team_root:
        ingest_team(team_root=args.team_root, out_root=args.out, mode=args.mode, written=written, stats=stats)

    print(json.dumps({"output": str(args.out), "stats": stats, "master_classes": len(nn_to_ing)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
