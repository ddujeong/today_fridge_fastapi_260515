#!/usr/bin/env python3
"""
n3_normalize_embedding.sql 은 psql 메타명령(\\copy, \\echo)과 Mac 경로가 포함되어 있어
Windows/CLI에서 그대로 실행하기 어렵다. 이 스크립트는 동일한 CSV를 STDIN COPY로 적재한 뒤
나머지 SQL을 실행한다.

사용 (backend2 루트):
  python app/crawler/apply/run_n3_normalize_embedding.py
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_URL = os.getenv("DB_URL", "postgresql://postgres:1234@localhost:5432/today_fridge")
CSV_PATH = ROOT / "app" / "crawler" / "apply" / "ingredient_normalization_candidates_approved_by_gpt.csv"


def main() -> None:
    db_url = os.getenv("DB_URL", DEFAULT_DB_URL)
    csv_path = Path(os.getenv("N3_CSV_PATH", str(CSV_PATH)))
    if not csv_path.is_file():
        raise SystemExit(f"CSV not found: {csv_path}")

    n3_sql_path = Path(__file__).resolve().parent / "n3_normalize_embedding.sql"
    raw = n3_sql_path.read_text(encoding="utf-8")

    # psql 메타명령 제거 후 두 덩이로 분리: \\copy 직전까지 / \\copy 직후부터
    lines = raw.splitlines()
    pre_copy: list[str] = []
    post_copy: list[str] = []
    mode = "pre"
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("\\copy "):
            mode = "post"
            continue
        if stripped.startswith("\\"):
            continue
        if mode == "pre":
            pre_copy.append(line)
        else:
            post_copy.append(line)

    pre_sql = "\n".join(pre_copy).strip()
    post_sql = "\n".join(post_copy).strip()

    copy_sql = """
        COPY tmp_ingredient_normalization_candidates
        (left_id, left_canonical_name, left_normalized_name, right_id, right_canonical_name,
         right_normalized_name, similarity, suggested_name, approved, memo)
        FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
    """

    with psycopg.connect(db_url, autocommit=False) as conn:
        conn.execute("SET search_path TO today_fridge, public")
        conn.execute(pre_sql)
        with conn.cursor() as cur:
            with cur.copy(copy_sql) as copy:
                with csv_path.open("rb") as f:
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
                        copy.write(chunk)
        conn.execute(post_sql)
        conn.commit()
    print("[OK] n3 CSV normalization applied")


if __name__ == "__main__":
    main()
