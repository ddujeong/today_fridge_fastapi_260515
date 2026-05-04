"""
Export YOLO classification label assets from PostgreSQL ingredient_master.

After ingredient_master is synced (e.g. 275 rows), regenerate:
  - model_label_to_master.json  — model class key -> displayName / normalizedName / category
  - ingredient_normalized_vocab.json — flat list of normalized_name for validation

YOLO classify folder names must match the **model class keys** in this JSON.
Keys use zero-padded ids so lexicographic order matches numeric order:
  ing_00001, ing_00042, ...

Dataset layout (train on any machine with GPU):
  <dataset>/train/ing_00123/*.jpg
  <dataset>/val/ing_00123/*.jpg

Usage:
  set DATABASE_URL=postgresql://USER:PASS@HOST:5432/today_fridge
  python export_yolo_label_assets_from_db.py --out-dir ../data

  # or JDBC-style URL base (script strips jdbc: prefix):
  python export_yolo_label_assets_from_db.py --db-url "postgresql://postgres:1234@localhost:5432/today_fridge"
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise SystemExit("install psycopg: pip install 'psycopg[binary]'") from exc


def jdbc_to_psycopg_url(url: str) -> str:
    u = url.strip()
    if u.startswith("jdbc:postgresql://"):
        return "postgresql://" + u[len("jdbc:postgresql://") :]
    return u


def model_key_for_ingredient_id(ingredient_id: int, width: int = 5) -> str:
    return f"ing_{int(ingredient_id):0{width}d}"


def fetch_rows(
    conn: Any,
    schema: str,
    active_only: bool,
) -> List[Tuple[int, str, str, str]]:
    active_clause = "AND (im.is_active IS NULL OR im.is_active = true)" if active_only else ""
    q = f"""
        SELECT im.ingredient_id,
               im.normalized_name,
               im.canonical_name,
               COALESCE(ic.category_name, '') AS category_name
        FROM {schema}.ingredient_master im
        LEFT JOIN {schema}.ingredient_category ic
          ON ic.category_id = im.category_id
        WHERE 1=1
        {active_clause}
        ORDER BY im.ingredient_id
    """
    with conn.cursor() as cur:
        cur.execute(q)
        rows = cur.fetchall()
    out: List[Tuple[int, str, str, str]] = []
    for rid, nn, canonical, cat in rows:
        out.append((int(rid), str(nn), str(canonical), str(cat or "")))
    return out


def build_label_map(
    rows: Sequence[Tuple[int, str, str, str]],
    key_width: int,
) -> Dict[str, Dict[str, Any]]:
    labels: Dict[str, Dict[str, Any]] = {}
    for ingredient_id, normalized_name, _canonical, category_name in rows:
        mk = model_key_for_ingredient_id(ingredient_id, width=key_width)
        labels[mk] = {
            "displayName": normalized_name,
            "normalizedName": normalized_name,
            "categorySuggestion": category_name or "",
            "ingredientId": ingredient_id,
        }
    return labels


def write_outputs(
    *,
    out_dir: Path,
    rows: Sequence[Tuple[int, str, str, str]],
    key_width: int,
    source_note: str,
    label_map_filename: str = "model_label_to_master.json",
    vocab_filename: str = "ingredient_normalized_vocab.json",
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    names_sorted = sorted({r[1] for r in rows})
    labels = build_label_map(rows, key_width=key_width)

    map_path = out_dir / label_map_filename
    vocab_path = out_dir / vocab_filename

    now = datetime.now(timezone.utc).isoformat()

    map_payload = {
        "schema": "model_label_to_master_v2_db_export",
        "description": (
            "YOLO class folder / model output label -> ingredient_master. "
            "Keys are zero-padded ing_XXXXX matching ingredient_id. "
            "Train/val image folders must use the same names."
        ),
        "generatedAt": now,
        "source": source_note,
        "labelKeyFormat": f"ing_{{:0{key_width}d}}",
        "labels": labels,
    }

    vocab_payload = {
        "schema": "ingredient_normalized_vocab_v2_db_export",
        "generatedAt": now,
        "source": source_note,
        "rowCount": len(rows),
        "distinctNormalizedNames": len(names_sorted),
        "names": names_sorted,
    }

    map_path.write_text(json.dumps(map_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    vocab_path.write_text(json.dumps(vocab_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {len(labels)} labels -> {map_path}")
    print(f"Wrote vocab ({len(names_sorted)} distinct names, {len(rows)} rows) -> {vocab_path}")


def resolve_db_url(explicit: Optional[str]) -> str:
    if explicit:
        return jdbc_to_psycopg_url(explicit)
    for key in ("DATABASE_URL", "DB_URL", "PGURL"):
        v = os.getenv(key)
        if v:
            return jdbc_to_psycopg_url(v)
    raise SystemExit(
        "Set DATABASE_URL (postgresql://...) or pass --db-url. "
        "Example: postgresql://postgres:1234@127.0.0.1:5432/today_fridge"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export YOLO label map + vocab from PostgreSQL")
    parser.add_argument(
        "--db-url",
        default=None,
        help="PostgreSQL URL (or set DATABASE_URL). jdbc:postgresql:// is accepted.",
    )
    parser.add_argument(
        "--schema",
        default=os.getenv("PGSCHEMA", "today_fridge"),
        help="Schema name (default: today_fridge)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data",
        help="Directory for model_label_to_master.json and ingredient_normalized_vocab.json",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Only rows where is_active is null or true",
    )
    parser.add_argument(
        "--key-width",
        type=int,
        default=5,
        help="Zero-pad width for ing_XXXXX (default 5)",
    )
    parser.add_argument(
        "--ingredient-ids",
        default="",
        help="comma-separated ingredient_id values; if set, export only these rows (order preserved)",
    )
    parser.add_argument(
        "--manifest-json",
        type=Path,
        default=None,
        help="ingredient_non_packaged_allowlist_resolved.json — export ids from resolutions (skips null)",
    )
    parser.add_argument(
        "--label-map-filename",
        default="model_label_to_master.json",
        help="output label map JSON filename under --out-dir",
    )
    parser.add_argument(
        "--vocab-filename",
        default="ingredient_normalized_vocab.json",
        help="output vocab JSON filename under --out-dir",
    )
    args = parser.parse_args()

    db_url = resolve_db_url(args.db_url)
    if "?" not in db_url and "options" not in db_url:
        pass  # search_path can be set via SET below

    source_note = re.sub(r":([^:@/]+)@", r":***@", db_url)

    id_filter: Optional[List[int]] = None
    if args.manifest_json and args.manifest_json.is_file():
        doc = json.loads(args.manifest_json.read_text(encoding="utf-8"))
        id_filter = []
        for r in doc.get("resolutions") or []:
            iid = r.get("ingredientId")
            if iid is not None:
                id_filter.append(int(iid))
        _ordered: List[int] = []
        _seen_ids: set[int] = set()
        for x in id_filter:
            if x not in _seen_ids:
                _seen_ids.add(x)
                _ordered.append(x)
        id_filter = _ordered
    elif str(args.ingredient_ids).strip():
        id_filter = [int(x.strip()) for x in str(args.ingredient_ids).split(",") if x.strip()]

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{args.schema}"')
        rows = fetch_rows(conn, schema=args.schema, active_only=args.active_only)

    if id_filter is not None:
        want = set(id_filter)
        rows = [row for row in rows if row[0] in want]
        # preserve manifest order when manifest provided
        if args.manifest_json and args.manifest_json.is_file():
            pos = {iid: idx for idx, iid in enumerate(id_filter)}
            rows = sorted(rows, key=lambda r: pos.get(r[0], 999999))

    if not rows:
        raise SystemExit(f"No rows returned from {args.schema}.ingredient_master (check schema / DB URL).")

    write_outputs(
        out_dir=args.out_dir,
        rows=rows,
        key_width=max(3, int(args.key_width)),
        source_note=f"postgresql {args.schema}.ingredient_master export ({source_note})",
        label_map_filename=args.label_map_filename,
        vocab_filename=args.vocab_filename,
    )

    example_key = model_key_for_ingredient_id(1, width=max(3, int(args.key_width)))
    print()
    print("Next: arrange training images as:")
    print(f"  <dataset>/train/{example_key}/*.jpg  (one folder per ingredient_id)")
    print("Then:")
    print("  yolo classify train model=yolov8n-cls.pt data=<dataset> epochs=80 imgsz=224 batch=16 device=0")


if __name__ == "__main__":
    main()
