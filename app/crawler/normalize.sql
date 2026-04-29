-- today_fridge 재료명 정규화 (보수적 규칙)
-- 대상: today_fridge.ingredient_master.normalized_name
-- 규칙:
-- 0) 줄바꿈(\n) 이후 제거
-- 1) 공백(띄어쓰기/탭) 제거
-- 2) 수식어 제거: 고운/가는/갈은/굵은
-- 3) 맨 앞 '꽃' 제거
-- 4) 표기 통일: 후추가루/후춧가루/후추 -> 후추
-- 5) 표기 통일: 달걀/계란 -> 달걀
-- 6) 표기 통일: 중력분/박력분/밀가루 -> 밀가루
-- 7) 잘못 과통합된 '장' 복구: normalized_name='장'이면 canonical_name 기반으로 재생성
-- 8) 과통합 방지: 결과가 '장'/'파'/'가루'이면 원형 유지

BEGIN;

UPDATE today_fridge.ingredient_master AS im
SET normalized_name = v.final_name
FROM (
    SELECT
        x.ingredient_id,
        CASE
            WHEN x.original_normalized_name = '장' THEN x.canonical_base_name
            WHEN x.mapped_name IN ('장', '파', '가루') THEN x.base_name
            ELSE x.mapped_name
        END AS final_name
    FROM (
        SELECT
            ingredient_id,
            original_normalized_name,
            base_name,
            canonical_base_name,
            CASE
                WHEN base_name IN ('후추가루', '후춧가루', '후추') THEN '후추'
                WHEN base_name IN ('달걀', '계란') THEN '달걀'
                WHEN base_name IN ('중력분', '박력분', '밀가루') THEN '밀가루'
                ELSE base_name
            END AS mapped_name
        FROM (
            SELECT
                ingredient_id,
                normalized_name AS original_normalized_name,
                TRIM(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                SPLIT_PART(normalized_name, E'\n', 1),
                                '\\s+',
                                '',
                                'g'
                            ),
                            '(고운|가는|갈은|굵은)',
                            '',
                            'g'
                        ),
                        '^꽃+',
                        ''
                    )
                ) AS base_name,
                TRIM(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                SPLIT_PART(canonical_name, E'\n', 1),
                                '\\s+',
                                '',
                                'g'
                            ),
                            '(고운|가는|갈은|굵은)',
                            '',
                            'g'
                        ),
                        '^꽃+',
                        ''
                    )
                ) AS canonical_base_name
            FROM today_fridge.ingredient_master
        ) s1
    ) x
) v
WHERE im.ingredient_id = v.ingredient_id
  AND im.normalized_name IS DISTINCT FROM v.final_name;

-- 9) normalized_name 기준 중복 ingredient_master 통합
-- keep_id: 동일 normalized_name 그룹의 최소 ingredient_id
CREATE TEMP TABLE tmp_ing_merge_map AS
SELECT
    ingredient_id AS old_id,
    MIN(ingredient_id) OVER (PARTITION BY normalized_name) AS keep_id
FROM today_fridge.ingredient_master;

-- 참조 FK 재매핑
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

-- substitute_graph 유니크 제약(uq_sub_pair) 충돌 정리
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

-- 중복 master 삭제
DELETE FROM today_fridge.ingredient_master im
USING tmp_ing_merge_map m
WHERE im.ingredient_id = m.old_id
  AND m.old_id <> m.keep_id;

COMMIT;
