\set ON_ERROR_STOP on

-- ============================================================
-- 오늘냉장고 ingredient_master 정규화 적용 SQL
-- 방식: CSV 파일을 읽어서 approved=Y 인 행만 반영
--
-- 기본 CSV 위치:
-- /Users/a0/Documents/git/project_final_backend_2/app/crawler/apply/ingredient_normalization_candidates_approved_by_gpt.csv
--
-- 실행 예:
-- psql -h localhost -p 5432 -U postgres -d today_fridge -f app/crawler/apply/apply_ingredient_normalization_from_csv.sql
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 0. 실행 전 카운트 확인
-- ------------------------------------------------------------
\echo '[BEFORE] ingredient_master row count / distinct normalized_name count'
SELECT
    COUNT(*) AS before_ingredient_master_rows,
    COUNT(DISTINCT normalized_name) FILTER (
        WHERE normalized_name IS NOT NULL AND normalized_name <> ''
    ) AS before_distinct_normalized_names
FROM today_fridge.ingredient_master;

-- ------------------------------------------------------------
-- 1. CSV 임시 적재 테이블 생성
-- ------------------------------------------------------------
DROP TABLE IF EXISTS tmp_ingredient_normalization_candidates;

CREATE TEMP TABLE tmp_ingredient_normalization_candidates (
    left_id text,
    left_canonical_name text,
    left_normalized_name text,
    right_id text,
    right_canonical_name text,
    right_normalized_name text,
    similarity text,
    suggested_name text,
    approved text,
    memo text
) ON COMMIT DROP;

-- ------------------------------------------------------------
-- 2. CSV 읽기
-- 주의: 이 경로는 psql을 실행하는 로컬 PC 기준 경로다.
-- 다른 위치에 두면 아래 FROM 경로만 수정하면 된다.
-- ------------------------------------------------------------
\copy tmp_ingredient_normalization_candidates (left_id, left_canonical_name, left_normalized_name, right_id, right_canonical_name, right_normalized_name, similarity, suggested_name, approved, memo) FROM '/Users/a0/Documents/git/project_final_backend_2/app/crawler/apply/ingredient_normalization_candidates_approved_by_gpt.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

\echo '[CSV] loaded rows / approved rows'
SELECT
    COUNT(*) AS loaded_rows,
    COUNT(*) FILTER (
        WHERE UPPER(TRIM(COALESCE(approved, ''))) IN ('Y', 'YES', 'TRUE', '1', '승인')
          AND TRIM(COALESCE(suggested_name, '')) <> ''
    ) AS approved_pair_rows
FROM tmp_ingredient_normalization_candidates;

-- ------------------------------------------------------------
-- 3. approved=Y 인 pair를 ingredient_id 단위로 펼치기
-- left_id, right_id 둘 다 같은 suggested_name으로 정규화한다.
-- ------------------------------------------------------------
DROP TABLE IF EXISTS tmp_approved_normalization_raw;

CREATE TEMP TABLE tmp_approved_normalization_raw AS
SELECT DISTINCT
    left_id::bigint AS ingredient_id,
    TRIM(suggested_name) AS suggested_name
FROM tmp_ingredient_normalization_candidates
WHERE UPPER(TRIM(COALESCE(approved, ''))) IN ('Y', 'YES', 'TRUE', '1', '승인')
  AND TRIM(COALESCE(suggested_name, '')) <> ''
  AND left_id ~ '^[0-9]+$'

UNION

SELECT DISTINCT
    right_id::bigint AS ingredient_id,
    TRIM(suggested_name) AS suggested_name
FROM tmp_ingredient_normalization_candidates
WHERE UPPER(TRIM(COALESCE(approved, ''))) IN ('Y', 'YES', 'TRUE', '1', '승인')
  AND TRIM(COALESCE(suggested_name, '')) <> ''
  AND right_id ~ '^[0-9]+$';

\echo '[APPROVED] affected ingredient_id count'
SELECT COUNT(*) AS affected_ingredient_ids
FROM tmp_approved_normalization_raw;

-- ------------------------------------------------------------
-- 4. 같은 ingredient_id가 서로 다른 suggested_name으로 승인된 경우 중단
-- 이 경우 사람이 CSV를 먼저 정리해야 한다.
-- ------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM tmp_approved_normalization_raw
        GROUP BY ingredient_id
        HAVING COUNT(DISTINCT suggested_name) > 1
    ) THEN
        RAISE EXCEPTION '같은 ingredient_id에 서로 다른 suggested_name이 승인되어 있습니다. 아래 conflict 조회 쿼리로 CSV를 먼저 정리하세요.';
    END IF;
END $$;

-- conflict 확인용. 정상이라면 0행이어야 한다.
\echo '[CHECK] conflicting approved names, should be empty'
SELECT
    ingredient_id,
    ARRAY_AGG(DISTINCT suggested_name ORDER BY suggested_name) AS conflicting_suggested_names
FROM tmp_approved_normalization_raw
GROUP BY ingredient_id
HAVING COUNT(DISTINCT suggested_name) > 1;

DROP TABLE IF EXISTS tmp_approved_normalization;

CREATE TEMP TABLE tmp_approved_normalization AS
SELECT
    ingredient_id,
    MIN(suggested_name) AS suggested_name
FROM tmp_approved_normalization_raw
GROUP BY ingredient_id;

-- ------------------------------------------------------------
-- 5. ingredient_master.normalized_name 업데이트
-- ------------------------------------------------------------
\echo '[UPDATE] normalized_name changes preview'
SELECT
    im.ingredient_id,
    im.canonical_name,
    im.normalized_name AS before_normalized_name,
    a.suggested_name AS after_normalized_name
FROM today_fridge.ingredient_master im
JOIN tmp_approved_normalization a
  ON a.ingredient_id = im.ingredient_id
WHERE im.normalized_name IS DISTINCT FROM a.suggested_name
ORDER BY im.ingredient_id
LIMIT 50;

UPDATE today_fridge.ingredient_master im
SET normalized_name = a.suggested_name
FROM tmp_approved_normalization a
WHERE im.ingredient_id = a.ingredient_id
  AND im.normalized_name IS DISTINCT FROM a.suggested_name;

\echo '[UPDATE] changed normalized_name row count'
SELECT COUNT(*) AS changed_normalized_name_count
FROM today_fridge.ingredient_master im
JOIN tmp_approved_normalization a
  ON a.ingredient_id = im.ingredient_id
WHERE im.normalized_name = a.suggested_name;

-- ------------------------------------------------------------
-- 6. 같은 normalized_name끼리 병합 맵 생성
-- 가장 작은 ingredient_id를 keep_id로 유지한다.
-- ------------------------------------------------------------
DROP TABLE IF EXISTS tmp_ing_merge_map;

CREATE TEMP TABLE tmp_ing_merge_map AS
SELECT
    ingredient_id AS old_id,
    MIN(ingredient_id) OVER (PARTITION BY normalized_name) AS keep_id,
    normalized_name
FROM today_fridge.ingredient_master
WHERE normalized_name IS NOT NULL
  AND normalized_name <> '';

\echo '[MERGE] ingredient_master rows to be merged'
SELECT COUNT(*) AS merge_target_ingredient_master_rows
FROM tmp_ing_merge_map
WHERE old_id <> keep_id;

-- ------------------------------------------------------------
-- 7. FK 참조를 keep_id로 이동
-- ------------------------------------------------------------
UPDATE today_fridge.recipe_ingredient ri
SET ingredient_master_id = m.keep_id
FROM tmp_ing_merge_map m
WHERE ri.ingredient_master_id = m.old_id
  AND m.old_id <> m.keep_id;

UPDATE today_fridge.user_ingredient ui
SET ingredient_master_id = m.keep_id
FROM tmp_ing_merge_map m
WHERE ui.ingredient_master_id = m.old_id
  AND m.old_id <> m.keep_id;

UPDATE today_fridge.shopping_item_mcp sm
SET ingredient_master_id = m.keep_id
FROM tmp_ing_merge_map m
WHERE sm.ingredient_master_id = m.old_id
  AND m.old_id <> m.keep_id;

UPDATE today_fridge.substitute_graph sg
SET base_ingredient_id = m.keep_id
FROM tmp_ing_merge_map m
WHERE sg.base_ingredient_id = m.old_id
  AND m.old_id <> m.keep_id;

UPDATE today_fridge.substitute_graph sg
SET sub_ingredient_id = m.keep_id
FROM tmp_ing_merge_map m
WHERE sg.sub_ingredient_id = m.old_id
  AND m.old_id <> m.keep_id;

-- ------------------------------------------------------------
-- 8. substitute_graph 중복 정리
-- ------------------------------------------------------------
DELETE FROM today_fridge.substitute_graph t
USING (
    SELECT ctid
    FROM (
        SELECT
            ctid,
            ROW_NUMBER() OVER (
                PARTITION BY base_ingredient_id, sub_ingredient_id, cooking_context
                ORDER BY ctid
            ) AS rn
        FROM today_fridge.substitute_graph
    ) d
    WHERE d.rn > 1
) dup
WHERE t.ctid = dup.ctid;

-- ------------------------------------------------------------
-- 9. ingredient_master 중복 삭제
-- ------------------------------------------------------------
DELETE FROM today_fridge.ingredient_master im
USING tmp_ing_merge_map m
WHERE im.ingredient_id = m.old_id
  AND m.old_id <> m.keep_id;

-- ------------------------------------------------------------
-- 10. 실행 후 결과 확인
-- ------------------------------------------------------------
\echo '[AFTER] ingredient_master row count / distinct normalized_name count'
SELECT
    COUNT(*) AS after_ingredient_master_rows,
    COUNT(DISTINCT normalized_name) FILTER (
        WHERE normalized_name IS NOT NULL AND normalized_name <> ''
    ) AS after_distinct_normalized_names
FROM today_fridge.ingredient_master;

\echo '[CHECK] remaining duplicate normalized_name groups'
SELECT
    normalized_name,
    COUNT(*) AS cnt,
    ARRAY_AGG(ingredient_id ORDER BY ingredient_id) AS ingredient_ids,
    ARRAY_AGG(canonical_name ORDER BY ingredient_id) AS canonical_names
FROM today_fridge.ingredient_master
WHERE normalized_name IS NOT NULL
  AND normalized_name <> ''
GROUP BY normalized_name
HAVING COUNT(*) > 1
ORDER BY cnt DESC, normalized_name
LIMIT 30;

COMMIT;

\echo '[DONE] CSV based ingredient normalization finished.'
