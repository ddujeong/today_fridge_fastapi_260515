"""
Run normalize.sql, then refresh YOLO label JSON and move train/val/test ing_* folders
when ingredient_id changes (merge / delete) but normalized_name is the anchor.

Usage (from project_final_backend_2):
  python app/models/ingredient/tools/post_normalize_ingredient_sync.py \\
    --db-url postgresql://postgres:1234@127.0.0.1:5432/today_fridge \\
    --normalize-sql app/crawler/normalize.sql

Optional:
  --dataset-root ml_datasets/ingredient_master_cls  (repeatable)
  --dataset-root data_sources/team_uploads
  --dry-run  (no SQL, no file moves; show remap only)
  --skip-normalize  (only export + migrate from current DB; use if SQL already applied)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise SystemExit("pip install 'psycopg[binary]'") from exc

_TOOL_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _TOOL_DIR.parents[3]
_DATA = _TOOL_DIR.parent / "data"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
SPLITS = ("train", "val", "test")


def jdbc_to_psycopg_url(url: str) -> str:
    u = url.strip()
    if u.startswith("jdbc:postgresql://"):
        return "postgresql://" + u[len("jdbc:postgresql://") :]
    return u


def resolve_db_url(explicit: Optional[str]) -> str:
    import os

    if explicit:
        return jdbc_to_psycopg_url(explicit)
    for key in ("DATABASE_URL", "DB_URL", "PGURL"):
        v = os.getenv(key)
        if v:
            return jdbc_to_psycopg_url(v)
    raise SystemExit("Pass --db-url or set DATABASE_URL")


def fetch_master_rows(conn: Any, schema: str) -> List[Tuple[int, str]]:
    q = f"""
        SELECT ingredient_id, COALESCE(normalized_name, '') AS nn
        FROM {schema}.ingredient_master
        ORDER BY ingredient_id
    """
    with conn.cursor() as cur:
        cur.execute(q)
        return [(int(r[0]), str(r[1])) for r in cur.fetchall()]


def nn_to_keep_id(rows: List[Tuple[int, str]]) -> Dict[str, int]:
    """After merge, one normalized_name should map to one surviving id (min id)."""
    m: Dict[str, int] = {}
    for iid, nn in rows:
        nn = nn.strip()
        if not nn:
            continue
        if nn not in m or iid < m[nn]:
            m[nn] = iid
    return m


def build_old_to_new(
    before: List[Tuple[int, str]],
    after: List[Tuple[int, str]],
) -> Dict[int, Optional[int]]:
    after_map = nn_to_keep_id(after)
    out: Dict[int, Optional[int]] = {}
    for oid, nn in before:
        nn = nn.strip()
        nid = after_map.get(nn)
        out[oid] = nid if nid is not None else None
    return out


def ing_key(iid: int, width: int = 5) -> str:
    return f"ing_{iid:0{width}d}"


def list_images(d: Path) -> List[Path]:
    if not d.is_dir():
        return []
    files = [p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXT]
    return sorted(files, key=lambda p: str(p).lower())


def migrate_split(
    *,
    dataset_root: Path,
    remap: Dict[int, Optional[int]],
    dry_run: bool,
    key_width: int,
) -> Dict[str, Any]:
    stats = {"moved_files": 0, "merged_folders": 0, "skipped_identity": 0, "orphan_old_ids": []}
    orphans: set[int] = set()
    for old_id, new_id in remap.items():
        if new_id is None:
            orphans.add(old_id)
        elif old_id == new_id:
            stats["skipped_identity"] += 1
    for split in SPLITS:
        split_root = dataset_root / split
        if not split_root.is_dir():
            continue
        for old_id, new_id in remap.items():
            if new_id is None or old_id == new_id:
                continue
            old_dir = split_root / ing_key(old_id, key_width)
            new_dir = split_root / ing_key(new_id, key_width)
            if not old_dir.is_dir():
                continue
            imgs = list_images(old_dir)
            if not imgs:
                if not dry_run:
                    try:
                        old_dir.rmdir()
                    except OSError:
                        pass
                continue
            stats["merged_folders"] += 1
            if dry_run:
                stats["moved_files"] += len(imgs)
                continue
            new_dir.mkdir(parents=True, exist_ok=True)
            for src in imgs:
                dest = new_dir / src.name
                if dest.exists():
                    stem, suf = dest.stem, dest.suffix
                    k = 1
                    while (new_dir / f"{stem}__dup{k}{suf}").exists():
                        k += 1
                    dest = new_dir / f"{stem}__dup{k}{suf}"
                shutil.move(str(src), str(dest))
                stats["moved_files"] += 1
            try:
                old_dir.rmdir()
            except OSError:
                pass
    stats["orphan_old_ids"] = sorted(orphans)
    return stats


def run_normalize_sql(conn: Any, sql_path: Path) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply normalize.sql, export labels, migrate ing_* image folders")
    parser.add_argument("--db-url", default=None)
    parser.add_argument("--schema", default="today_fridge")
    parser.add_argument(
        "--normalize-sql",
        type=Path,
        default=_BACKEND_ROOT / "app" / "crawler" / "normalize.sql",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        action="append",
        default=[],
        help="repeat for each dataset root (train/val/test/ing_* below)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-normalize", action="store_true", help="skip SQL; use current DB state")
    parser.add_argument("--skip-migrate", action="store_true")
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--key-width", type=int, default=5)
    parser.add_argument(
        "--remap-audit",
        type=Path,
        default=_DATA / "post_normalize_ingredient_remap.json",
        help="write old_id -> new_id JSON for audit",
    )
    args = parser.parse_args()

    db_url = resolve_db_url(args.db_url)
    sql_path = args.normalize_sql.resolve()
    if not args.skip_normalize and not sql_path.is_file():
        raise SystemExit(f"Missing --normalize-sql: {sql_path}")

    default_roots = [
        _BACKEND_ROOT / "ml_datasets" / "ingredient_master_cls",
        _BACKEND_ROOT / "data_sources" / "team_uploads",
    ]
    roots = [Path(p).resolve() for p in (args.dataset_root or default_roots)]

    before: Optional[List[Tuple[int, str]]] = None
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{args.schema}"')
        before = fetch_master_rows(conn, args.schema)

        if not args.skip_normalize:
            run_normalize_sql(conn, sql_path)
        conn.commit()

        after = fetch_master_rows(conn, args.schema)

    assert before is not None
    remap_int = build_old_to_new(before, after)
    remap_out = {str(k): (v if v is not None else None) for k, v in sorted(remap_int.items())}
    audit = {
        "beforeCount": len(before),
        "afterCount": len(after),
        "remap": remap_out,
        "note": "null new_id = row removed from ingredient_master (e.g. merged away or alpha delete)",
    }
    args.remap_audit.parent.mkdir(parents=True, exist_ok=True)
    args.remap_audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"audit": str(args.remap_audit.resolve()), "summary": audit}, ensure_ascii=False, indent=2))

    if not args.skip_export:
        sys.path.insert(0, str(_BACKEND_ROOT))
        from app.models.ingredient.tools.export_yolo_label_assets_from_db import (  # noqa: E402
            fetch_rows,
            write_outputs,
        )
        import re as _re
        source_note = _re.sub(r":([^:@/]+)@", r":***@", db_url)
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(f'SET search_path TO "{args.schema}"')
            rows = fetch_rows(conn, schema=args.schema, active_only=False)
        write_outputs(
            out_dir=_DATA,
            rows=rows,
            key_width=args.key_width,
            source_note=f"postgresql {args.schema}.ingredient_master export ({source_note}) post_normalize",
        )

        # Full alias list aligned to new model folders (search_en from seed only).
        import subprocess

        alias_py = _TOOL_DIR / "export_ingredient_image_alias_template.py"
        subprocess.run(
            [
                sys.executable,
                str(alias_py),
                "--master-json",
                str(_DATA / "model_label_to_master.json"),
                "--dataset-root",
                str(_BACKEND_ROOT / "ml_datasets" / "ingredient_master_cls"),
                "--include-covered",
                "--out",
                str(_DATA / "ingredient_image_search_aliases.json"),
            ],
            cwd=str(_BACKEND_ROOT),
            check=True,
        )

    if args.skip_migrate:
        print(json.dumps({"migrate": "skipped"}, ensure_ascii=False))
        return

    all_stats = {}
    for root in roots:
        if not root.exists():
            all_stats[str(root)] = {"skipped": "path missing"}
            continue
        st = migrate_split(dataset_root=root, remap=remap_int, dry_run=args.dry_run, key_width=args.key_width)
        all_stats[str(root)] = st
    print(json.dumps({"migrate": all_stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
