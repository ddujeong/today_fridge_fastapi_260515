#!/usr/bin/env python3
"""
데이터베이스에서 중복 레시피를 제거하는 스크립트
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Optional

import psycopg
from psycopg import sql

# --- Helper classes/functions adapted from app/crawler/import_recipe_csvs_to_postgres_v3.py ---

class DbMeta:
    def __init__(self, conn, schema: str):
        self.conn = conn
        self.schema = schema
        self._columns_cache: dict[str, set[str]] = {}
        self._pk_cache: dict[str, str] = {}
        self._timestamp_cols_cache: dict[str, Optional[str]] = {} # Cache for timestamp columns

    def columns(self, table: str) -> set[str]:
        if table not in self._columns_cache:
            rows = self.conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                ORDER BY ordinal_position
                """,
                (self.schema, table),
            ).fetchall()
            self._columns_cache[table] = {r[0] for r in rows}
        return self._columns_cache[table]

    def has(self, table: str, column: str) -> bool:
        return column in self.columns(table)

    def pick(self, table: str, candidates: list[str], required: bool = False) -> Optional[str]:
        cols = self.columns(table)
        for c in candidates:
            if c in cols:
                return c
        if required:
            raise RuntimeError(f"{table} 테이블에서 필요한 컬럼을 찾지 못했습니다. candidates={candidates}, actual={sorted(cols)}")
        return None

    def pk(self, table: str) -> str:
        if table not in self._pk_cache:
            rows = self.conn.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                 AND tc.table_name = kcu.table_name
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = %s
                  AND tc.table_name = %s
                ORDER BY kcu.ordinal_position
                """,
                (self.schema, table),
            ).fetchall()

            if rows:
                self._pk_cache[table] = rows[0][0]
            else:
                cols = self.columns(table)
                fallback_candidates = [
                    f"{table}_id",
                    table.rstrip("s") + "_id",
                    "id",
                ]
                found = None
                for c in fallback_candidates:
                    if c in cols:
                        found = c
                        break
                if not found:
                    raise RuntimeError(f"{table} 테이블의 PK를 찾지 못했습니다. actual={sorted(cols)}")
                self._pk_cache[table] = found

        return self._pk_cache[table]

    def get_timestamp_column(self, table: str) -> Optional[str]:
        """Finds a column that likely stores creation or update timestamp."""
        if table in self._timestamp_cols_cache:
            return self._timestamp_cols_cache[table]

        cols = self.columns(table)
        # Common timestamp column names
        timestamp_candidates = [
            "created_at", "created_date", "creation_date",
            "updated_at", "updated_date", "last_modified",
            "timestamp", "date_created", "date_updated"
        ]
        for col in timestamp_candidates:
            if col in cols:
                self._timestamp_cols_cache[table] = col
                return col

        self._timestamp_cols_cache[table] = None
        return None


def q_ident(name: str):
    return sql.Identifier(name)


def get_tables(conn, schema: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_type = 'BASE TABLE'
        """,
        (schema,),
    ).fetchall()
    return {r[0] for r in rows}

# --- End of helper functions ---

def parse_args():
    parser = argparse.ArgumentParser(description="Remove duplicate recipes from the database.")
    parser.add_argument("--db-url", required=True, help="Database connection URL (e.g., postgresql://user:password@host:port/dbname)")
    parser.add_argument("--schema", default="public", help="Database schema to use (default: public)")
    parser.add_argument("--dry-run", action="store_true", help="If set, only report duplicates without deleting them.")
    return parser.parse_args()

def find_and_delete_duplicates(db_url: str, schema: str, dry_run: bool):
    """
    Finds duplicate recipes in the database and deletes them, keeping the oldest one.
    """
    tables_with_children_to_clean = ["recipe_ingredient", "recipe_step"]

    with psycopg.connect(db_url) as conn:
        meta = DbMeta(conn, schema)

        # Set search_path
        conn.execute(sql.SQL("SET search_path TO {}").format(q_ident(schema)))

        if "recipes" not in get_tables(conn, schema):
            print(f"Error: 'recipes' table not found in schema '{schema}'.")
            sys.exit(1)

        recipe_pk = meta.pk("recipes")
        source_site_col = meta.pick("recipes", ["source_site", "sourceSite"], required=False)
        source_key_col = meta.pick("recipes", ["source_recipe_key", "source_recipe_id", "sourceRecipeKey"], required=False)
        title_col = meta.pick("recipes", ["title", "name", "recipe_name"], required=False)
        created_at_col = meta.get_timestamp_column("recipes")

        if not source_key_col and not title_col:
            print("Error: Cannot identify recipes. Neither 'source_recipe_key' nor 'title' columns found in 'recipes' table.")
            sys.exit(1)

        print(f"Using PK: '{recipe_pk}'")
        if source_site_col: print(f"Using source_site column: '{source_site_col}'")
        if source_key_col: print(f"Using source_recipe_key column: '{source_key_col}'")
        if title_col: print(f"Using title column as fallback: '{title_col}'")
        if created_at_col: print(f"Using '{created_at_col}' for determining which duplicate to keep.")
        else: print("Warning: No clear timestamp column found. Keeping the one with the lowest PK value as 'oldest'.")

        # Fetch all relevant data for duplicate detection
        final_select_cols = [
            sql.SQL(f"r.{recipe_pk} AS recipe_id"),
        ]
        group_key_parts = []

        if source_site_col:
            final_select_cols.append(sql.SQL(f"r.{source_site_col} AS source_site"))
            group_key_parts.append(q_ident(source_site_col))
        else:
            final_select_cols.append(sql.SQL("'N/A' AS source_site"))
            # If source_site_col is not present, we don't include it in the SQL GROUP BY.
            # The Python logic will use ('N/A', group_key) as the identifier.

        if source_key_col:
            final_select_cols.append(sql.SQL(f"r.{source_key_col} AS group_key"))
            group_key_parts.append(q_ident(source_key_col))
        else:
            final_select_cols.append(sql.SQL(f"r.{title_col} AS group_key"))
            group_key_parts.append(q_ident(title_col))

        if created_at_col:
            final_select_cols.append(sql.SQL(f"r.{created_at_col} AS keep_value"))
        else:
            final_select_cols.append(sql.SQL(f"r.{recipe_pk} AS keep_value")) # Fallback to PK

        query_all_recipes_data = sql.SQL("SELECT {} FROM {}.recipes r").format(
            sql.SQL(", ").join(final_select_cols),
            schema=q_ident(schema)
        )

        all_recipe_data = conn.execute(query_all_recipes_data).fetchall()

        # Dictionary to store recipe IDs per group, and the ID to keep for that group
        # {(site, key): {'ids': [id1, id2, ...], 'keep_id': id_to_keep, 'min_keep_val': min_value}}
        duplicates_map = {}
        # Dictionary to count items per group for quick duplicate check
        group_counts = {}

        for row in all_recipe_data:
            recipe_id = row[0]
            source_site = row[1]
            group_key = row[2]
            keep_value = row[3]

            group_identifier = (source_site, group_key) # Tuple for unique group identification

            if group_identifier not in duplicates_map:
                duplicates_map[group_identifier] = {'ids': [], 'keep_id': None, 'min_keep_val': None}
                group_counts[group_identifier] = 0

            duplicates_map[group_identifier]['ids'].append(recipe_id)
            group_counts[group_identifier] += 1

            # Determine which ID to keep for this group (the one with the minimum keep_value)
            current_min_keep_val = duplicates_map[group_identifier]['min_keep_val']
            if current_min_keep_val is None or keep_value < current_min_keep_val:
                duplicates_map[group_identifier]['min_keep_val'] = keep_value
                duplicates_map[group_identifier]['keep_id'] = recipe_id # This is the ID to keep

        # Collect IDs to delete
        ids_to_delete = []
        total_recipes_in_duplicate_groups = 0
        total_recipes_to_delete = 0

        for group_identifier, data in duplicates_map.items():
            if group_counts[group_identifier] > 1: # It's a duplicate group
                total_recipes_in_duplicate_groups += group_counts[group_identifier]
                recipe_ids_in_group = data['ids']
                id_to_keep = data['keep_id']

                # All IDs in the group except the one to keep are duplicates
                for recipe_id in recipe_ids_in_group:
                    if recipe_id != id_to_keep:
                        ids_to_delete.append(recipe_id)
                        total_recipes_to_delete += 1

        if not ids_to_delete:
            print("No duplicate recipes found.")
            return

        print(f"Found {total_recipes_in_duplicate_groups} recipes in duplicate groups. Identified {total_recipes_to_delete} recipes for deletion.")

        if dry_run:
            print("
--- Dry Run ---")
            print("The following recipe IDs would be deleted:")
            for i, recipe_id in enumerate(ids_to_delete):
                print(f"  - {recipe_id}")
                if i >= 20: # Limit output for dry run
                    print("  ...")
                    break
            print("--- End Dry Run ---")
            return

        # Proceed with deletion
        print(f"
Deleting {total_recipes_to_delete} duplicate recipes...")

        # Prepare delete statements
        delete_recipe_query_template = sql.SQL("DELETE FROM {schema}.recipes WHERE {pk_col} = %s").format(
            schema=q_ident(schema),
            pk_col=q_ident(recipe_pk)
        )

        # Delete associated children first to avoid foreign key constraint issues
        for child_table in tables_with_children_to_clean:
            if child_table not in get_tables(conn, schema):
                print(f"Warning: Child table '{child_table}' not found. Skipping cleanup for this table.")
                continue

            child_recipe_fk = meta.pick(child_table, ["recipe_id", "recipe"], required=False)
            if not child_recipe_fk:
                print(f"Warning: Foreign key to recipes table not found in '{child_table}'. Skipping cleanup for this table.")
                continue

            # Batch delete child records for the IDs to be deleted
            print(f"Cleaning up '{child_table}'...")
            # Construct query for batch deletion
            delete_child_query = sql.SQL("DELETE FROM {schema}.{child_table} WHERE {fk_col} IN ({ids})").format(
                schema=q_ident(schema),
                child_table=q_ident(child_table),
                fk_col=q_ident(child_recipe_fk),
                ids=sql.SQL(", ").join(sql.Placeholder() for _ in ids_to_delete)
            )
            try:
                # Execute batch delete. psycopg handles the list of IDs for IN clause.
                conn.execute(delete_child_query, ids_to_delete)
                print(f"Cleaned up {len(ids_to_delete)} records in '{child_table}'.")
            except Exception as e:
                print(f"Error cleaning up '{child_table}': {e}")
                conn.rollback() # Rollback if child deletion fails
                sys.exit(1)


        # Now delete the recipes themselves
        deleted_count = 0
        for recipe_id in ids_to_delete:
            try:
                conn.execute(delete_recipe_query_template, (recipe_id,))
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting recipe with ID {recipe_id}: {e}")
                conn.rollback() # Rollback on error
                sys.exit(1)

        conn.commit()
        print(f"Successfully deleted {deleted_count} duplicate recipes.")


def main():
    args = parse_args()
    try:
        find_and_delete_duplicates(args.db_url, args.schema, args.dry_run)
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
