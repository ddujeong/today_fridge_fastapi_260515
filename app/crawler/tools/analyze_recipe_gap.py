"""Analyze CSV ordinal vs DB for recipe_id gap 257-315 (one-off diagnostic)."""

from __future__ import annotations

import csv
import sys
import argparse
from pathlib import Path

import psycopg
from psycopg import sql

# run from repo root: python app/crawler/tools/analyze_recipe_gap.py
CRAWLER = Path(__file__).resolve().parents[1]
if str(CRAWLER) not in sys.path:
    sys.path.insert(0, str(CRAWLER))

import import_recipe_csvs_to_postgres_v3 as imp  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db-url", default="postgresql://postgres:1234@localhost:5432/today_fridge")
    p.add_argument("--schema", default="today_fridge")
    p.add_argument("--source-site", default="MyCrawler")
    p.add_argument("--input", default=str(CRAWLER / "recipes_result"))
    p.add_argument("--allow-empty-steps", action="store_true")
    p.add_argument("--gap-start", type=int, default=257)
    p.add_argument("--gap-end", type=int, default=315)
    args = p.parse_args()

    db_url = args.db_url
    schema = args.schema
    source_site = args.source_site
    input_dir = Path(args.input)
    gap = range(args.gap_start, args.gap_end + 1)

    with psycopg.connect(db_url) as conn:
        schema = imp.resolve_schema(conn, schema, ["ingredient_master", "recipes", "recipe_ingredient", "recipe_step"])
        conn.execute(sql.SQL("SET search_path TO {}").format(imp.q_ident(schema)))
        meta = imp.DbMeta(conn, schema)

        missing_db = set(gap)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT recipe_id FROM {schema}.recipes WHERE recipe_id = ANY(%s)",
                (list(gap),),
            )
            for (rid,) in cur.fetchall():
                missing_db.discard(rid)

        seq = 0
        remap = {}
        no_match = []
        for csv_file in imp.collect_csv_files(str(input_dir)):
            with csv_file.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    title = imp.get_first(row, ["title"], "")
                    ingredients = imp.parse_list_cell(imp.get_first(row, ["ingredients"], ""))
                    steps = imp.parse_list_cell(imp.get_first(row, ["steps"], ""))
                    if not title or not ingredients:
                        continue
                    if not steps and not args.allow_empty_steps:
                        continue
                    seq += 1
                    if seq not in missing_db:
                        continue
                    img = imp.get_first(row, ["img", "thumbnail_url", "thumbnailUrl"])
                    source_url = imp.get_first(row, ["source_url", "sourceUrl", "url"])
                    sk = imp.make_source_key(title, source_url, img)
                    ex = imp.find_existing_recipe(conn, meta, source_site, sk, title)
                    if ex is not None:
                        remap[seq] = ex
                    else:
                        no_match.append((seq, title[:50]))

        print("missing in DB:", sorted(missing_db))
        print("CSV ordinal -> existing recipe_id (same source_key):", len(remap))
        for k in sorted(remap)[:20]:
            print(f"  {k} -> {remap[k]}")
        if len(remap) > 20:
            print("  ...")
        print("no existing row for CSV row (need fresh insert):", len(no_match))
        for t in no_match[:15]:
            print(" ", t)


if __name__ == "__main__":
    main()
