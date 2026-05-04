#!/usr/bin/env python3
"""
오늘냉장고 레시피 CSV -> PostgreSQL 적재 스크립트

1. 루트폴더에서 pip install -r requirements.txt로 의존성 다운로드
2. f5 누르기

대상 CSV 컬럼 예시:
- img
- title
- quantity
- time
- difficulty
- ingredients
- steps

특징:
- ingredient_master의 PK가 ingredient_master_id든 id든 자동 감지
- recipes / recipe_ingredient / recipe_step 주요 컬럼명 자동 감지
- ingredients, steps가 Python 리스트 문자열이어도 ast.literal_eval로 처리
- 조리 단계가 빈 레시피는 기본 스킵
"""

import argparse
import ast
import csv
import hashlib
import os
from pathlib import Path
from typing import Any, Optional

import psycopg
from psycopg import sql


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


DEFAULT_INPUT = os.getenv("RECIPE_CSV_INPUT", "app/crawler/recipes_result/")
DEFAULT_DB_URL = os.getenv("DB_URL", "postgresql://postgres:1234@localhost:5432/today_fridge")
DEFAULT_SCHEMA = os.getenv("DB_SCHEMA", "today_fridge")
DEFAULT_SOURCE_SITE = os.getenv("SOURCE_SITE", "MyCrawler")
DEFAULT_ALLOW_EMPTY_STEPS = env_bool("ALLOW_EMPTY_STEPS", True)
DEFAULT_DRY_RUN = env_bool("DRY_RUN", False)


def parse_args():
    parser = argparse.ArgumentParser(
        description="오늘냉장고 레시피 CSV를 PostgreSQL에 적재합니다. 인자가 없으면 VSCode F5용 기본값을 사용합니다."
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help=f"CSV 파일 또는 CSV들이 들어 있는 폴더. 기본값: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--db-url",
        default=DEFAULT_DB_URL,
        help="예: postgresql://postgres:1234@localhost:5432/today_fridge",
    )
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    parser.add_argument("--source-site", default=DEFAULT_SOURCE_SITE)
    parser.add_argument(
        "--allow-empty-steps",
        default=DEFAULT_ALLOW_EMPTY_STEPS,
        action=argparse.BooleanOptionalAction,
        help="조리 단계가 비어 있는 레시피도 적재합니다. 비활성화: --no-allow-empty-steps",
    )
    parser.add_argument(
        "--dry-run",
        default=DEFAULT_DRY_RUN,
        action=argparse.BooleanOptionalAction,
        help="DB에 적재하지 않고 파싱만 확인합니다. 비활성화: --no-dry-run",
    )
    return parser.parse_args()


class DbMeta:
    def __init__(self, conn, schema: str):
        self.conn = conn
        self.schema = schema
        self._columns_cache: dict[str, set[str]] = {}
        self._pk_cache: dict[str, str] = {}

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


def q_ident(name: str):
    return sql.Identifier(name)


def get_first(row: dict[str, Any], keys: list[str], default: Optional[str] = None) -> Optional[str]:
    for key in keys:
        v = row.get(key)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return default


def make_source_key(title: str, source_url: Optional[str] = None, img_url: Optional[str] = None) -> str:
    base = f"{title}|{source_url or ''}|{img_url or ''}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:32]


def parse_list_cell(value: Any) -> list[Any]:
    if value is None:
        return []

    text = str(value).strip()
    if not text:
        return []

    # CSV가 "[{'name': '...', 'quantity': '...'}]" 같은 Python literal 형태인 경우
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except Exception:
        pass

    # fallback
    if "\n" in text:
        parts = text.splitlines()
    elif "|" in text:
        parts = text.split("|")
    elif ";;" in text:
        parts = text.split(";;")
    else:
        parts = [text]

    return [p.strip(" \t\r\n-") for p in parts if p.strip(" \t\r\n-")]


def normalize_ingredient_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        name = (
            item.get("name")
            or item.get("ingredient")
            or item.get("rawName")
            or item.get("raw_text")
            or ""
        )
        quantity = (
            item.get("quantity")
            or item.get("amount")
            or item.get("amountText")
            or item.get("amount_text")
        )
        unit = item.get("unit")
        is_optional = bool(item.get("isOptional") or item.get("is_optional") or False)
    else:
        name = str(item)
        quantity = None
        unit = None
        is_optional = False

    name = str(name).strip()
    quantity = str(quantity).strip() if quantity is not None and str(quantity).strip() else None

    return {
        "raw_text": name if quantity is None else f"{name} {quantity}",
        "normalized_name": name,
        "amount_text": quantity,
        "unit": unit,
        "is_optional": is_optional,
    }


def normalize_step_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        text = (
            item.get("text")
            or item.get("instruction")
            or item.get("instructionText")
            or item.get("instruction_text")
            or item.get("description")
            or ""
        )
        img = item.get("img") or item.get("image") or item.get("imageUrl") or item.get("step_image_url")
    else:
        text = str(item)
        img = None

    return {
        "instruction_text": str(text).strip(),
        "step_image_url": img,
    }


def insert_dynamic(conn, meta: DbMeta, table: str, values: dict[str, Any], returning_col: Optional[str] = None) -> Optional[Any]:
    values = {k: v for k, v in values.items() if k and meta.has(table, k)}

    if not values:
        raise RuntimeError(f"{table}에 넣을 수 있는 컬럼이 없습니다.")

    cols = list(values.keys())
    vals = [values[c] for c in cols]

    query = sql.SQL("INSERT INTO {schema}.{table} ({cols}) VALUES ({placeholders})").format(
        schema=q_ident(meta.schema),
        table=q_ident(table),
        cols=sql.SQL(", ").join(map(q_ident, cols)),
        placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in cols),
    )

    if returning_col:
        query += sql.SQL(" RETURNING {ret}").format(ret=q_ident(returning_col))
        row = conn.execute(query, vals).fetchone()
        return row[0] if row else None

    conn.execute(query, vals)
    return None


def select_one_by(conn, meta: DbMeta, table: str, where_col: str, where_val: Any, return_col: str) -> Optional[Any]:
    if not meta.has(table, where_col):
        return None

    query = sql.SQL("SELECT {ret} FROM {schema}.{table} WHERE {where_col} = %s LIMIT 1").format(
        ret=q_ident(return_col),
        schema=q_ident(meta.schema),
        table=q_ident(table),
        where_col=q_ident(where_col),
    )
    row = conn.execute(query, (where_val,)).fetchone()
    return row[0] if row else None


def ensure_unknown_category(conn, meta: DbMeta) -> Optional[Any]:
    if "ingredient_category" not in get_tables(conn, meta.schema):
        return None

    pk = meta.pk("ingredient_category")
    code_col = meta.pick("ingredient_category", ["category_code", "code"], required=False)
    name_col = meta.pick("ingredient_category", ["category_name", "name"], required=False)
    sort_col = meta.pick("ingredient_category", ["sort_order", "display_order"], required=False)
    active_col = meta.pick("ingredient_category", ["is_active", "active"], required=False)

    if code_col:
        existing = select_one_by(conn, meta, "ingredient_category", code_col, "UNKNOWN", pk)
        if existing:
            return existing

    values = {}
    if code_col:
        values[code_col] = "UNKNOWN"
    if name_col:
        values[name_col] = "미분류"
    if sort_col:
        values[sort_col] = 999
    if active_col:
        values[active_col] = True

    if not values:
        return None

    try:
        return insert_dynamic(conn, meta, "ingredient_category", values, pk)
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        if code_col:
            return select_one_by(conn, meta, "ingredient_category", code_col, "UNKNOWN", pk)
        return None


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


def resolve_schema(conn, requested_schema: str, required_tables: list[str]) -> str:
    requested_tables = get_tables(conn, requested_schema)
    if all(t in requested_tables for t in required_tables):
        return requested_schema

    rows = conn.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        """
    ).fetchall()

    by_schema: dict[str, set[str]] = {}
    for schema_name, table_name in rows:
        by_schema.setdefault(schema_name, set()).add(table_name)

    best_schema = requested_schema
    best_score = -1
    for schema_name, table_names in by_schema.items():
        score = sum(1 for t in required_tables if t in table_names)
        if score > best_score:
            best_schema = schema_name
            best_score = score

    if best_score > 0 and best_schema != requested_schema:
        print(
            f"[INFO] 요청한 schema='{requested_schema}'에서 필수 테이블을 찾지 못해 "
            f"schema='{best_schema}'로 자동 전환합니다."
        )
        return best_schema

    return requested_schema


def ensure_ingredient_master(conn, meta: DbMeta, normalized_name: str, category_id: Optional[Any]) -> Optional[Any]:
    if not normalized_name:
        return None

    pk = meta.pk("ingredient_master")
    name_col = meta.pick("ingredient_master", ["normalized_name", "name", "ingredient_name"], required=True)
    canonical_col = meta.pick("ingredient_master", ["canonical_name", "canonicalName"], required=False)
    category_fk_col = meta.pick("ingredient_master", ["category_id", "ingredient_category_id"], required=False)
    alias_col = meta.pick("ingredient_master", ["alias_text", "aliases"], required=False)
    standard_unit_col = meta.pick("ingredient_master", ["standard_unit"], required=False)
    active_col = meta.pick("ingredient_master", ["is_active", "active"], required=False)
    created_col = meta.pick("ingredient_master", ["created_at", "created_date"], required=False)
    updated_col = meta.pick("ingredient_master", ["updated_at", "updated_date"], required=False)

    existing = select_one_by(conn, meta, "ingredient_master", name_col, normalized_name, pk)
    if existing:
        return existing

    values = {
        name_col: normalized_name,
    }

    # 실제 DB에서 canonical_name이 NOT NULL인 경우가 있으므로 normalized_name과 같은 값으로 채운다.
    if canonical_col and canonical_col != name_col:
        values[canonical_col] = normalized_name

    if category_fk_col and category_id is not None:
        values[category_fk_col] = category_id
    if alias_col:
        values[alias_col] = None
    if standard_unit_col:
        values[standard_unit_col] = "g"
    if active_col:
        values[active_col] = True

    # created_at / updated_at은 DB default가 없는 경우가 있으므로 CURRENT_TIMESTAMP를 쓴다.
    # insert_dynamic은 값 바인딩만 하므로 SQL 함수를 직접 넣지 않고 Python에서 생략한다.
    # 실제 DB에 DEFAULT now()가 있으면 자동으로 채워진다.

    try:
        return insert_dynamic(conn, meta, "ingredient_master", values, pk)
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        return select_one_by(conn, meta, "ingredient_master", name_col, normalized_name, pk)


def find_existing_recipe(conn, meta: DbMeta, source_site: str, source_key: str, title: str) -> Optional[Any]:
    pk = meta.pk("recipes")

    source_site_col = meta.pick("recipes", ["source_site", "sourceSite"], required=False)
    source_key_col = meta.pick("recipes", ["source_recipe_key", "source_recipe_id", "sourceRecipeKey"], required=False)

    if source_site_col and source_key_col:
        query = sql.SQL(
            "SELECT {pk} FROM {schema}.recipes WHERE {site_col} = %s AND {key_col} = %s LIMIT 1"
        ).format(
            pk=q_ident(pk),
            schema=q_ident(meta.schema),
            site_col=q_ident(source_site_col),
            key_col=q_ident(source_key_col),
        )
        row = conn.execute(query, (source_site, source_key)).fetchone()
        if row:
            return row[0]

    title_col = meta.pick("recipes", ["title", "name", "recipe_name"], required=False)
    if title_col:
        return select_one_by(conn, meta, "recipes", title_col, title, pk)

    return None


def ensure_recipe(conn, meta: DbMeta, row: dict[str, Any], source_site: str) -> Any:
    pk = meta.pk("recipes")

    title = get_first(row, ["title"], "")
    img = get_first(row, ["img", "thumbnail_url", "thumbnailUrl"])
    servings = get_first(row, ["quantity", "servings", "servings_text"])
    cook_time = get_first(row, ["time", "cook_time", "cook_time_text"])
    difficulty = get_first(row, ["difficulty"])
    source_url = get_first(row, ["source_url", "sourceUrl", "url"])

    source_key = make_source_key(title, source_url, img)

    existing = find_existing_recipe(conn, meta, source_site, source_key, title)
    if existing:
        return existing

    values = {}

    mapping = {
        "source_site": source_site,
        "source_recipe_key": source_key,
        "title": title,
        "thumbnail_url": img,
        "difficulty_level": difficulty,
        "difficulty": difficulty,
        "servings_text": servings,
        "quantity": servings,
        "cook_time_text": cook_time,
        "cooking_time": cook_time,
        "source_url": source_url,
        "is_active": True,
    }

    for col, val in mapping.items():
        if meta.has("recipes", col):
            values[col] = val

    # title 계열 컬럼 보정
    title_col = meta.pick("recipes", ["title", "name", "recipe_name"], required=True)
    values[title_col] = title

    # 생성/수정 시간은 DB default가 없을 수도 있으므로 실제 컬럼이 있으면 psycopg가 now()를 못 넣지 않도록 SQL 함수 대신 Python 없이 생략.
    # PostgreSQL DDL에서 DEFAULT now()가 없는 경우에는 아래에서 NOT NULL 오류가 날 수 있음.
    # 그런 경우 created_at/updated_at 컬럼 기본값을 DB에 추가하는 편이 좋음.

    return insert_dynamic(conn, meta, "recipes", values, pk)


def delete_children(conn, meta: DbMeta, recipe_id: Any):
    for table in ["recipe_ingredient", "recipe_step"]:
        if table not in get_tables(conn, meta.schema):
            continue
        recipe_fk = meta.pick(table, ["recipe_id", "recipe"], required=False)
        if not recipe_fk:
            continue

        query = sql.SQL("DELETE FROM {schema}.{table} WHERE {recipe_fk} = %s").format(
            schema=q_ident(meta.schema),
            table=q_ident(table),
            recipe_fk=q_ident(recipe_fk),
        )
        conn.execute(query, (recipe_id,))


def insert_recipe_ingredients(conn, meta: DbMeta, recipe_id: Any, ingredients: list[Any], category_id: Optional[Any]) -> int:
    table = "recipe_ingredient"
    recipe_fk = meta.pick(table, ["recipe_id", "recipe"], required=True)
    master_fk = meta.pick(table, ["ingredient_master_id", "ingredient_id", "master_ingredient_id"], required=False)
    raw_col = meta.pick(table, ["raw_text", "raw_name", "name", "ingredient_name"], required=True)
    normalized_col = meta.pick(table, ["normalized_name_snapshot", "normalized_name"], required=False)
    amount_col = meta.pick(table, ["amount_text", "amount", "quantity"], required=False)
    unit_col = meta.pick(table, ["unit"], required=False)
    optional_col = meta.pick(table, ["is_optional", "optional"], required=False)
    sort_col = meta.pick(table, ["sort_order", "step_order", "display_order"], required=False)

    count = 0

    for idx, item in enumerate(ingredients, start=1):
        parsed = normalize_ingredient_item(item)
        if not parsed["raw_text"]:
            continue

        master_id = ensure_ingredient_master(conn, meta, parsed["normalized_name"], category_id)

        values = {
            recipe_fk: recipe_id,
            raw_col: parsed["raw_text"],
        }

        if master_fk and master_id is not None:
            values[master_fk] = master_id
        if normalized_col:
            values[normalized_col] = parsed["normalized_name"]
        if amount_col:
            values[amount_col] = parsed["amount_text"]
        if unit_col:
            values[unit_col] = parsed["unit"]
        if optional_col:
            values[optional_col] = parsed["is_optional"]
        if sort_col:
            values[sort_col] = idx

        insert_dynamic(conn, meta, table, values, None)
        count += 1

    return count


def insert_recipe_steps(conn, meta: DbMeta, recipe_id: Any, steps: list[Any]) -> int:
    table = "recipe_step"
    recipe_fk = meta.pick(table, ["recipe_id", "recipe"], required=True)
    step_no_col = meta.pick(table, ["step_no", "step_number", "step_order", "sort_order"], required=False)
    text_col = meta.pick(table, ["instruction_text", "content", "description", "step_text"], required=True)
    image_col = meta.pick(table, ["step_image_url", "image_url", "img"], required=False)

    count = 0

    for idx, item in enumerate(steps, start=1):
        parsed = normalize_step_item(item)
        if not parsed["instruction_text"]:
            continue

        values = {
            recipe_fk: recipe_id,
            text_col: parsed["instruction_text"],
        }

        if step_no_col:
            values[step_no_col] = idx
        if image_col:
            values[image_col] = parsed["step_image_url"]

        insert_dynamic(conn, meta, table, values, None)
        count += 1

    return count


def find_project_root() -> Path:
    """
    VSCode에서 F5로 실행할 때 cwd가 달라져도
    app/crawler/recipes_result 같은 프로젝트 루트 기준 경로를 찾기 위한 보정.
    """
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / "app" / "crawler").exists():
            return parent
    return Path.cwd()


def resolve_input_path(input_path: str) -> Path:
    p = Path(input_path).expanduser()
    if p.is_absolute():
        return p

    cwd_candidate = (Path.cwd() / p).resolve()
    if cwd_candidate.exists():
        return cwd_candidate

    root_candidate = (find_project_root() / p).resolve()
    if root_candidate.exists():
        return root_candidate

    # 존재하지 않는 경우에도 에러 메시지에 실제 확인 경로가 나오도록 cwd 기준으로 반환
    return cwd_candidate


def collect_csv_files(input_path: str) -> list[Path]:
    p = resolve_input_path(input_path)
    if p.is_file():
        return [p]
    return sorted(p.glob("*.csv"))


def import_files(args):
    input_path = resolve_input_path(args.input)
    files = collect_csv_files(args.input)
    if not files:
        raise RuntimeError(f"CSV 파일을 찾지 못했습니다: {input_path}")

    stats = {
        "files": len(files),
        "rows": 0,
        "imported": 0,
        "skipped": 0,
        "failed": 0,
        "ingredients": 0,
        "steps": 0,
    }

    required_tables = ["ingredient_master", "recipes", "recipe_ingredient", "recipe_step"]

    with psycopg.connect(args.db_url) as conn:
        schema = resolve_schema(conn, args.schema, required_tables)
        meta = DbMeta(conn, schema)

        # search_path 설정
        conn.execute(sql.SQL("SET search_path TO {}").format(q_ident(schema)))

        print("[SCHEMA CHECK]")
        print(f"- using schema: {schema}")
        for table in required_tables:
            print(f"- {table}: pk={meta.pk(table)}, columns={sorted(meta.columns(table))}")

        category_id = ensure_unknown_category(conn, meta)

        if args.dry_run:
            print("\n[DRY-RUN] DB에는 적재하지 않고 파싱만 확인합니다.")

        for csv_file in files:
            print(f"\n[FILE] {csv_file}")

            with csv_file.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)

                for line_no, row in enumerate(reader, start=2):
                    stats["rows"] += 1

                    title = get_first(row, ["title"], "")
                    ingredients = parse_list_cell(get_first(row, ["ingredients"], ""))
                    steps = parse_list_cell(get_first(row, ["steps"], ""))

                    try:
                        if not title:
                            stats["skipped"] += 1
                            print(f"[SKIP] line={line_no} reason=empty title")
                            continue

                        if not ingredients:
                            stats["skipped"] += 1
                            print(f"[SKIP] line={line_no} title={title!r} reason=empty ingredients")
                            continue

                        if not steps and not args.allow_empty_steps:
                            stats["skipped"] += 1
                            print(f"[SKIP] line={line_no} title={title!r} reason=empty steps")
                            continue

                        if args.dry_run:
                            stats["imported"] += 1
                            stats["ingredients"] += len(ingredients)
                            stats["steps"] += len(steps)
                            continue

                        with conn.transaction():
                            recipe_id = ensure_recipe(conn, meta, row, args.source_site)
                            delete_children(conn, meta, recipe_id)
                            ing_count = insert_recipe_ingredients(conn, meta, recipe_id, ingredients, category_id)
                            step_count = insert_recipe_steps(conn, meta, recipe_id, steps)

                        stats["imported"] += 1
                        stats["ingredients"] += ing_count
                        stats["steps"] += step_count

                    except Exception as e:
                        stats["failed"] += 1
                        print(f"[FAIL] line={line_no} title={title!r} reason={e}")

    print("\n[DONE]")
    for k, v in stats.items():
        print(f"{k:11}: {v}")


def print_run_config(args):
    print("[RUN CONFIG]")
    print(f"- input             : {resolve_input_path(args.input)}")
    print(f"- db_url            : {args.db_url}")
    print(f"- schema            : {args.schema}")
    print(f"- source_site       : {args.source_site}")
    print(f"- allow_empty_steps : {args.allow_empty_steps}")
    print(f"- dry_run           : {args.dry_run}")
    print()


def main():
    args = parse_args()
    print_run_config(args)
    import_files(args)


if __name__ == "__main__":
    main()
