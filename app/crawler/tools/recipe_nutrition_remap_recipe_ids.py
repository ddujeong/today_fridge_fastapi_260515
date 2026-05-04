"""
After del_deduplicated_recipes.py, some recipe_id values are deleted but the same
logical recipes remain under new PKs. Team recipe_nutrition INSERT files still
reference old ids (e.g. 257..315).

This script walks the same CSV order as import_recipe_csvs_to_postgres_v3.py and
maps old ordinal recipe_id -> current PK via (source_site, source_recipe_key).

Usage (repo root):
  python app/crawler/tools/recipe_nutrition_remap_recipe_ids.py \\
    --nutrition-sql app/crawler/apply/recipe_nutrition_inserts.sql \\
    --out app/crawler/apply/recipe_nutrition_inserts_remapped.sql

  python app/crawler/tools/recipe_nutrition_remap_recipe_ids.py \\
    --nutrition-sql app/crawler/apply/recipe_nutrition_inserts.sql \\
    --apply --db-url postgresql://postgres:1234@localhost:5432/today_fridge
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import psycopg
from psycopg import sql

import sys

CRAWLER = Path(__file__).resolve().parents[1]
if str(CRAWLER) not in sys.path:
    sys.path.insert(0, str(CRAWLER))

import import_recipe_csvs_to_postgres_v3 as imp


def build_ordinal_to_recipe_id_map(
    conn,
    meta: imp.DbMeta,
    schema: str,
    source_site: str,
    input_dir: Path,
    allow_empty_steps: bool,
) -> dict[int, int]:
    """Simulate import row order; return {ordinal: current recipe_id in DB}."""
    ordinal = 0
    mapping: dict[int, int] = {}

    for csv_file in imp.collect_csv_files(str(input_dir)):
        with csv_file.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = imp.get_first(row, ["title"], "")
                ingredients = imp.parse_list_cell(imp.get_first(row, ["ingredients"], ""))
                steps = imp.parse_list_cell(imp.get_first(row, ["steps"], ""))
                if not title or not ingredients:
                    continue
                if not steps and not allow_empty_steps:
                    continue

                ordinal += 1
                img = imp.get_first(row, ["img", "thumbnail_url", "thumbnailUrl"])
                source_url = imp.get_first(row, ["source_url", "sourceUrl", "url"])
                sk = imp.make_source_key(title, source_url, img)
                rid = imp.find_existing_recipe(conn, meta, source_site, sk, title)
                if rid is None:
                    raise RuntimeError(
                        f"No DB recipe for CSV ordinal={ordinal} title={title!r} "
                        f"(re-import or fix CSV paths)"
                    )
                mapping[ordinal] = int(rid)

    return mapping


def _remap_insert_line(line: str, ordinal_to_id: dict[int, int]) -> tuple[str, bool | None]:
    """Nutrition INSERT: first value is recipe_id. Team export used CSV import order as PK."""
    if "recipe_nutrition" not in line.lower() or "values" not in line.lower():
        return line, None
    m = re.search(r"(VALUES\s*\()\s*(\d+)", line, re.IGNORECASE)
    if not m:
        return line, None
    old_id = int(m.group(2))
    if old_id not in ordinal_to_id:
        raise KeyError(
            f"No CSV ordinal {old_id} in mapping (nutrition row references unknown recipe index)"
        )
    new_id = ordinal_to_id[old_id]
    i, j = m.span(2)
    new_line = line[:i] + str(new_id) + line[j:]
    return new_line, new_id != old_id


def remap_nutrition_sql(text: str, ordinal_to_id: dict[int, int]) -> tuple[str, int, int, int]:
    """Returns (text, changed_count, unchanged_count, skipped_duplicate_target_ids)."""
    changed = 0
    unchanged = 0
    skipped_dup = 0
    out_lines: list[str] = []
    seen_target_id: set[int] = set()

    for line in text.splitlines():
        new_line, did_change = _remap_insert_line(line, ordinal_to_id)
        if did_change is not None:
            m2 = re.search(r"VALUES\s*\(\s*(\d+)", new_line, re.IGNORECASE)
            if m2:
                target_id = int(m2.group(1))
                if target_id in seen_target_id:
                    skipped_dup += 1
                    continue
                seen_target_id.add(target_id)
        out_lines.append(new_line)
        if did_change is True:
            changed += 1
        elif did_change is False:
            unchanged += 1

    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(out_lines) + trailing, changed, unchanged, skipped_dup


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default="postgresql://postgres:1234@localhost:5432/today_fridge")
    ap.add_argument("--schema", default="today_fridge")
    ap.add_argument("--source-site", default="MyCrawler")
    ap.add_argument("--input", default=str(CRAWLER / "recipes_result"))
    ap.add_argument("--allow-empty-steps", action="store_true")
    ap.add_argument("--nutrition-sql", required=True)
    ap.add_argument("--out")
    ap.add_argument("--apply", action="store_true", help="Execute remapped SQL on DB")
    args = ap.parse_args()

    input_dir = Path(args.input)
    nutrition_path = Path(args.nutrition_sql)

    with psycopg.connect(args.db_url) as conn:
        schema = imp.resolve_schema(
            conn, args.schema, ["ingredient_master", "recipes", "recipe_ingredient", "recipe_step"]
        )
        conn.execute(sql.SQL("SET search_path TO {}").format(imp.q_ident(schema)))
        meta = imp.DbMeta(conn, schema)
        ordinal_to_id = build_ordinal_to_recipe_id_map(
            conn, meta, schema, args.source_site, input_dir, args.allow_empty_steps
        )

    raw = nutrition_path.read_text(encoding="utf-8")
    remapped, changed, _, skipped_dup = remap_nutrition_sql(raw, ordinal_to_id)

    print(f"[MAP] CSV import ordinals mapped: {len(ordinal_to_id)}")
    gap_fixes = [(o, ordinal_to_id[o]) for o in range(257, 316) if ordinal_to_id.get(o) != o]
    print(f"[GAP] ordinals 257..315 where id changed: {len(gap_fixes)}")
    for o, nid in gap_fixes[:5]:
        print(f"  ordinal {o} -> recipe_id {nid}")
    if len(gap_fixes) > 5:
        print("  ...")
    print(f"[SQL] recipe_id values rewritten in INSERT lines: {changed}")
    if skipped_dup:
        print(
            f"[DEDUP] skipped {skipped_dup} INSERT(s) that targeted the same recipe_id "
            f"(duplicate CSV rows merged to one ingredient_master / recipe)"
        )

    if args.out:
        Path(args.out).write_text(remapped, encoding="utf-8")
        print(f"[OUT] {args.out}")

    if args.apply:
        with psycopg.connect(args.db_url) as conn:
            conn.execute(remapped)
            conn.commit()
        print("[OK] executed on DB")


if __name__ == "__main__":
    main()
