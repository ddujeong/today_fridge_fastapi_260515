"""
Map a team share folder (e.g. D:\\final_project\\Team_temp01) into data_sources/team_uploads/{train,val,test}/ing_XXXXX/.

If `--source` contains `train/`, `val/`, `test/` subfolders, each is scanned the same way (Grocery coarse names,
Korean names, or ing_* folders). `__MACOSX` is skipped.

Usage (backend_2 root):

  python app/models/ingredient/tools/ingest_team_temp_folders_to_train.py \\
    --source D:/final_project/Team_temp01 \\
    --team-out-root data_sources/team_uploads

Then merge into ml_datasets:

  python app/models/ingredient/tools/assemble_ingredient_master_cls_dataset.py \\
    --master-json app/models/ingredient/data/model_label_to_master.json \\
    --team-root data_sources/team_uploads \\
    --out ml_datasets/ingredient_master_cls \\
    --mode copy
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
DEFAULT_SPLITS = ("train", "val", "test")


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_grocery_coarse_to_normalized(map_path: Path) -> Dict[str, str]:
    """Grocery coarse folder (English) -> ingredient_master normalized_name (Korean)."""
    if not map_path.is_file():
        return {}
    data = load_json(map_path)
    out: Dict[str, str] = {}
    for grp in ("Fruit", "Vegetables"):
        block = data.get(grp) or {}
        if not isinstance(block, dict):
            continue
        for coarse, nn in block.items():
            out[str(coarse)] = str(nn).strip()
    return out


def build_folder_name_to_ing(master_path: Path) -> Tuple[Dict[str, str], List[str]]:
    """Map folder label (Korean name as typed in DB) -> ing_XXXXX. Warns on duplicate keys."""
    data = load_json(master_path)
    labels = data.get("labels") or {}
    key_to_ing: Dict[str, str] = {}
    warnings: List[str] = []
    for ing_key, meta in labels.items():
        if not isinstance(meta, dict):
            continue
        for field in ("normalizedName", "normalized_name", "displayName", "display_name"):
            raw = meta.get(field)
            if not raw:
                continue
            k = str(raw).strip()
            if not k:
                continue
            if k in key_to_ing and key_to_ing[k] != ing_key:
                warnings.append(f"duplicate name '{k}' -> {key_to_ing[k]} vs {ing_key} (keeping first)")
                continue
            if k not in key_to_ing:
                key_to_ing[k] = str(ing_key)
    return key_to_ing, warnings


def iter_images(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            yield p


def safe_dst_name(prefix: str, src: Path, used: Set[str]) -> str:
    base = f"{prefix}__{src.name}"
    if base not in used:
        used.add(base)
        return base
    stem, suf = Path(base).stem, Path(base).suffix
    i = 1
    while f"{stem}_{i}{suf}" in used:
        i += 1
    out = f"{stem}_{i}{suf}"
    used.add(out)
    return out


def ingest_one_split(
    *,
    scan_root: Path,
    split_name: str,
    team_out_root: Path,
    name_to_ing: Dict[str, str],
    coarse_to_nn: Dict[str, str],
    mode: str,
) -> Dict[str, Any]:
    st: Dict[str, Any] = {
        "split": split_name,
        "scan_root": str(scan_root),
        "folders_seen": 0,
        "images_copied": 0,
        "skipped_no_match": 0,
        "unmatched": [],
    }
    if not scan_root.is_dir():
        st["skipped"] = "not a directory"
        return st

    for child in sorted(scan_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name == "__MACOSX" or child.name.startswith("."):
            continue
        st["folders_seen"] += 1
        label = child.name.strip()
        if label.startswith("ing_"):
            ing = label
        else:
            ing = name_to_ing.get(label)
            if not ing:
                nn = coarse_to_nn.get(label)
                if nn:
                    ing = name_to_ing.get(nn)
        if not ing:
            st["skipped_no_match"] += 1
            st["unmatched"].append(label)
            continue

        dest_dir = team_out_root / split_name / ing
        used_names: Set[str] = set()
        prefix = f"teamtemp_{split_name}_{label.replace(' ', '_')[:36]}"
        for img in iter_images(child):
            fname = safe_dst_name(prefix, img, used_names)
            dst = dest_dir / fname
            if mode == "copy":
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(img, dst)
            st["images_copied"] += 1
    return st


def main() -> None:
    here = Path(__file__).resolve().parent
    default_master = here.parent / "data" / "model_label_to_master.json"
    default_grocery_map = here.parent / "data" / "grocery_coarse_folder_to_normalized_name.json"
    parser = argparse.ArgumentParser(description="Ingest Team_temp train/val/test into team_uploads")
    parser.add_argument("--source", type=Path, default=Path(r"D:\final_project\Team_temp01"))
    parser.add_argument("--master-json", type=Path, default=default_master)
    parser.add_argument("--grocery-coarse-map", type=Path, default=default_grocery_map)
    parser.add_argument(
        "--team-out-root",
        type=Path,
        default=Path("data_sources/team_uploads"),
        help="Same as assemble --team-root (contains train/, val/, test/)",
    )
    parser.add_argument(
        "--splits",
        type=str,
        default=",".join(DEFAULT_SPLITS),
        help="Comma-separated: train,val,test",
    )
    parser.add_argument("--mode", choices=["copy", "dry-run"], default="copy")
    args = parser.parse_args()

    if not args.master_json.is_file():
        print(f"Missing --master-json: {args.master_json}", file=sys.stderr)
        sys.exit(2)
    if not args.source.is_dir():
        print(json.dumps({"warn": "source not found, nothing to do", "source": str(args.source)}, ensure_ascii=False))
        sys.exit(0)

    name_to_ing, dup_warnings = build_folder_name_to_ing(args.master_json)
    for w in dup_warnings:
        print(w, file=sys.stderr)

    coarse_to_nn = load_grocery_coarse_to_normalized(args.grocery_coarse_map)
    splits = [s.strip() for s in args.splits.split(",") if s.strip()]

    has_subsplit = any((args.source / s).is_dir() for s in DEFAULT_SPLITS)
    results: List[Dict[str, Any]] = []
    if has_subsplit:
        for sp in splits:
            scan = args.source / sp
            results.append(
                ingest_one_split(
                    scan_root=scan,
                    split_name=sp,
                    team_out_root=args.team_out_root,
                    name_to_ing=name_to_ing,
                    coarse_to_nn=coarse_to_nn,
                    mode=args.mode,
                )
            )
    else:
        # Flat layout: only one folder of classes → train
        results.append(
            ingest_one_split(
                scan_root=args.source,
                split_name="train",
                team_out_root=args.team_out_root,
                name_to_ing=name_to_ing,
                coarse_to_nn=coarse_to_nn,
                mode=args.mode,
            )
        )

    totals = {"folders_seen": 0, "images_copied": 0, "skipped_no_match": 0}
    all_unmatched: List[str] = []
    for r in results:
        totals["folders_seen"] += r.get("folders_seen", 0)
        totals["images_copied"] += r.get("images_copied", 0)
        totals["skipped_no_match"] += r.get("skipped_no_match", 0)
        all_unmatched.extend(r.get("unmatched") or [])

    print(
        json.dumps(
            {
                "source": str(args.source),
                "team_out_root": str(args.team_out_root),
                "mode": args.mode,
                "splits": splits if has_subsplit else ["train (flat source)"],
                "by_split": results,
                "totals": totals,
                "unmatched_all_splits": sorted(set(all_unmatched)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
