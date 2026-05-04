"""Audit DB ingredient_master vs model_label_to_master.json vs aliases; prune orphan ing_* folders.

Usage:
  python app/models/ingredient/tools/audit_ingredient_assets_vs_db.py
  python app/models/ingredient/tools/audit_ingredient_assets_vs_db.py --prune-orphans
  python app/models/ingredient/tools/audit_ingredient_assets_vs_db.py --prune-orphans \\
    --dataset-root ml_datasets/ingredient_master_cls --dataset-root data_sources/team_uploads
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import psycopg

_TOOL_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _TOOL_DIR.parents[3]
_DATA = _TOOL_DIR.parent / "data"
ING = re.compile(r"^ing_(\d+)$", re.I)

SPLITS = ("train", "val", "test")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit ingredient JSON + dataset folders vs DB")
    parser.add_argument("db_url", nargs="?", default="postgresql://postgres:1234@127.0.0.1:5432/today_fridge")
    parser.add_argument(
        "--prune-orphans",
        action="store_true",
        help="remove dataset ing_* folders whose id is not in ingredient_master (all splits)",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        action="append",
        dest="dataset_roots",
        default=None,
        help="repeat for each dataset root (default: ml_datasets/ingredient_master_cls only)",
    )
    args = parser.parse_args()
    db = args.db_url
    schema = "today_fridge"

    roots: list[Path]
    if args.dataset_roots:
        roots = [Path(p).resolve() for p in args.dataset_roots]
    else:
        roots = [_BACKEND_ROOT / "ml_datasets" / "ingredient_master_cls"]

    with psycopg.connect(db) as conn:
        with conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}"')
            cur.execute(
                "SELECT ingredient_id, normalized_name FROM ingredient_master ORDER BY ingredient_id"
            )
            db_rows = cur.fetchall()

    db_map = {int(r[0]): str(r[1]) for r in db_rows}
    db_ids = set(db_map)

    master_path = _DATA / "model_label_to_master.json"
    master = json.loads(master_path.read_text(encoding="utf-8"))
    labels = master.get("labels") or {}

    json_ids: set[int] = set()
    issues: list[str] = []
    for k, v in labels.items():
        m = ING.match(str(k))
        if not m:
            continue
        iid = int(m.group(1))
        json_ids.add(iid)
        exp_nn = db_map.get(iid)
        got_nn = str(v.get("normalizedName") or "")
        if iid not in db_map:
            issues.append(f"extra JSON key {k}: not in DB")
        elif exp_nn != got_nn:
            issues.append(f"nn mismatch {k}: JSON={got_nn!r} DB={exp_nn!r}")

    for iid in sorted(db_ids - json_ids):
        issues.append(f"missing JSON for DB id {iid} ({db_map[iid]!r})")

    aliases_path = _DATA / "ingredient_image_search_aliases.json"
    aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
    seen_alias_ids: set[int] = set()
    for e in aliases.get("entries") or []:
        folder = str(e.get("model_folder") or "")
        raw_id = e.get("ingredient_id")
        if raw_id is None:
            issues.append("alias entry missing ingredient_id")
            continue
        iid = int(raw_id)
        seen_alias_ids.add(iid)
        m = ING.match(folder)
        if not m or int(m.group(1)) != iid:
            issues.append(f"alias folder/id mismatch {folder!r} ingredient_id={iid}")
        if iid not in db_ids:
            issues.append(f"alias dead id {iid}")
        else:
            ann = str(e.get("normalized_name") or "")
            if ann != db_map[iid]:
                issues.append(f"alias nn id {iid}: file={ann!r} db={db_map[iid]!r}")

    for iid in sorted(db_ids - seen_alias_ids):
        issues.append(f"missing alias entry for DB id {iid}")
    for iid in sorted(seen_alias_ids - db_ids):
        issues.append(f"alias extra id {iid} not in DB")

    by_root: dict[str, dict] = {}
    for ds_root in roots:
        orphan: list[str] = []
        for split in SPLITS:
            sp = ds_root / split
            if not sp.is_dir():
                continue
            for p in sorted(sp.iterdir()):
                if not p.is_dir() or not p.name.startswith("ing_"):
                    continue
                m = ING.match(p.name)
                if not m:
                    continue
                oid = int(m.group(1))
                if oid not in db_ids and p.name not in orphan:
                    orphan.append(p.name)

        pruned: list[str] = []
        if args.prune_orphans and orphan:
            for name in orphan:
                for split in SPLITS:
                    folder = ds_root / split / name
                    if folder.is_dir():
                        shutil.rmtree(folder, ignore_errors=True)
                        pruned.append(f"{split}/{name}")

        by_root[str(ds_root)] = {
            "orphan_ing_folders": orphan,
            "pruned": pruned if args.prune_orphans else None,
        }

    print(
        json.dumps(
            {
                "db_rows": len(db_rows),
                "model_label_ids": len(json_ids),
                "alias_entries": len(seen_alias_ids),
                "issue_count": len(issues),
                "issues": issues[:80],
                "more_issues": max(0, len(issues) - 80),
                "datasets": by_root,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    raise SystemExit(1 if issues else 0)


if __name__ == "__main__":
    main()
