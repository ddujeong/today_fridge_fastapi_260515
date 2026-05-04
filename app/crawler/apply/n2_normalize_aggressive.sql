-- today_fridge ingredient_master 공격적 규칙 기반 정규화 + 100% 일치 병합
-- 목적:
-- 1) normalized_name/canonical_name에서 수식어 제거, 띄어쓰기 제거, 줄바꿈 이후 제거
-- 2) 말 되는 수준의 alias를 canonical 재료명으로 통일
-- 3) 최종 normalized_name이 100% 같은 ingredient_master는 하나로 병합
-- 4) recipe_ingredient / user_ingredient / shopping_item_mcp / substitute_graph FK를 keep_id로 이동 후 중복 master 삭제
--
-- 실행 전 권장 백업:
-- pg_dump -h localhost -p 5432 -U postgres -d today_fridge -F c -f before_ingredient_normalization.dump
--
-- 실행:
-- psql -h localhost -p 5432 -U postgres -d today_fridge -f normalize_ingredient_master_aggressive.sql

BEGIN;

SET search_path TO today_fridge, public;

DROP TABLE IF EXISTS tmp_ing_before_counts;
DROP TABLE IF EXISTS tmp_ing_normalization_preview;
DROP TABLE IF EXISTS tmp_ing_merge_map;

CREATE TEMP TABLE tmp_ing_before_counts AS
SELECT
    COUNT(*) AS ingredient_master_rows,
    COUNT(DISTINCT normalized_name) FILTER (
        WHERE normalized_name IS NOT NULL AND normalized_name <> ''
    ) AS distinct_normalized_names
FROM today_fridge.ingredient_master;

-- 정규화 함수는 pg_temp에만 생성되므로 현재 세션/실행 중에만 존재한다.
CREATE OR REPLACE FUNCTION pg_temp.normalize_today_fridge_ingredient_name(input_text text)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    raw text;
    v text;
BEGIN
    IF input_text IS NULL THEN
        RETURN NULL;
    END IF;

    -- 4) \n 있으면 \n부터 끝까지 제거
    raw := split_part(input_text, E'\n', 1);
    raw := split_part(raw, E'\r', 1);
    raw := btrim(raw);

    IF raw = '' THEN
        RETURN NULL;
    END IF;

    v := raw;

    -- 1) 수식어 제거
    -- 복합 표현은 띄어쓰기 차이를 흡수해서 먼저 제거한다.
    v := regexp_replace(v, '편으로\s*썬', '', 'g');
    v := regexp_replace(v, '데친\s*것', '', 'g');
    v := regexp_replace(v, '다진\s*것', '', 'g');

    v := regexp_replace(
        v,
        '(고운|가는|갈은|굵은|노란|빨간|시원한|작은것|녹색부분|삶은|흰부분|범일|단단한|채썬|데쳐서|물기짠|작은거)',
        '',
        'g'
    );

    -- '깐'은 보통 수식어이므로 앞쪽에서 제거한다.
    v := regexp_replace(v, '^(깐)+', '', 'g');

    -- '꽃'은 꽃소금 같은 수식어에는 제거하되, 꽃게는 보존한다.
    IF v NOT LIKE '꽃게%' THEN
        v := regexp_replace(v, '^(꽃)+', '', 'g');
    END IF;

    -- 3) 띄어쓰기/탭 제거
    v := regexp_replace(v, '\s+', '', 'g');
    v := btrim(v);

    -- 제거 결과가 비면 원문에서 공백만 제거한 값으로 복구
    IF v = '' THEN
        v := regexp_replace(raw, '\s+', '', 'g');
    END IF;

    -- 2) alias 매핑
    -- 너무 위험한 과통합은 피하고, 레시피 추천에서 같은 재료로 보는 게 자연스러운 수준만 매핑한다.
    v := CASE
        -- 기본 표기 통일
        WHEN v IN ('후추가루', '후추', '후춧가루') THEN '후춧가루'
        WHEN v IN ('계란', '달걀') THEN '달걀'
        WHEN v IN ('고추가루', '고춧가루') THEN '고춧가루'
        WHEN v IN ('중력분', '박력분', '강력분', '밀가루') THEN '밀가루'

        -- 소금/설탕
        WHEN v IN ('소금', '꽃소금', '굵은소금', '천일염', '맛소금') THEN '소금'
        WHEN v IN ('설탕', '흰설탕', '백설탕', '황설탕', '흑설탕', '갈색설탕', '자일로스설탕') THEN '설탕'

        -- 장/소스류: 초고추장/쌈장처럼 별도 재료는 일부러 제외
        WHEN v IN ('고추장', '태양초고추장', '찰고추장', '순창고추장') THEN '고추장'
        WHEN v IN ('된장', '재래식된장', '집된장') THEN '된장'
        WHEN v IN ('간장', '진간장', '양조간장', '국간장', '조선간장', '맛간장') THEN '간장'
        WHEN v IN ('굴소스', '프리미엄굴소스') THEN '굴소스'
        WHEN v IN ('케찹', '케첩', '토마토케첩') THEN '케첩'
        WHEN v IN ('마요네즈', '마요네스') THEN '마요네즈'
        WHEN v IN ('식초', '양조식초', '현미식초', '사과식초') THEN '식초'
        WHEN v IN ('맛술', '미림', '요리술') THEN '맛술'
        WHEN v IN ('액젓', '멸치액젓', '까나리액젓') THEN '액젓'
        WHEN v IN ('멸치육수', '멸치다시마육수', '다시마육수', '육수') THEN '육수'

        -- 오일류
        WHEN v IN ('식용유', '카놀라유', '포도씨유', '해바라기씨유', '콩기름') THEN '식용유'
        WHEN v IN ('올리브유', '올리브오일') THEN '올리브유'
        WHEN v IN ('참기름', '참기름약간') THEN '참기름'
        WHEN v IN ('들기름', '들기름약간') THEN '들기름'

        -- 향신/가루류
        WHEN v IN ('고운고춧가루', '굵은고춧가루', '청양고춧가루') THEN '고춧가루'
        WHEN v IN ('깨', '참깨', '통깨', '볶은깨') THEN '참깨'
        WHEN v IN ('전분', '감자전분', '옥수수전분') THEN '전분'
        WHEN v IN ('베이킹파우더', '베이킹파우다') THEN '베이킹파우더'

        -- 채소류
        WHEN v IN ('마늘', '다진마늘', '간마늘', '통마늘') THEN '마늘'
        WHEN v IN ('생강', '다진생강', '간생강') THEN '생강'
        WHEN v IN ('양파', '양파채', '자색양파', '적양파') THEN '양파'
        WHEN v IN ('대파', '파', '대파흰대', '대파흰부분', '대파녹색부분', '흰대파') THEN '대파'
        WHEN v IN ('청양고추', '청양고추개') THEN '청양고추'
        WHEN v IN ('홍고추', '붉은고추') THEN '홍고추'
        WHEN v IN ('고추', '풋고추') THEN '고추'
        WHEN v IN ('당근', '당근채') THEN '당근'
        WHEN v IN ('감자', '감자개') THEN '감자'
        WHEN v IN ('무', '무우') THEN '무'
        WHEN v IN ('배추', '알배추', '알배기배추') THEN '배추'
        WHEN v IN ('양배추', '양배추잎') THEN '양배추'
        WHEN v IN ('깻잎', '깻잎장') THEN '깻잎'
        WHEN v IN ('부추', '영양부추') THEN '부추'
        WHEN v IN ('애호박', '호박') THEN '애호박'
        WHEN v IN ('오이', '백오이') THEN '오이'
        WHEN v IN ('가지', '가지개') THEN '가지'

        -- 버섯류
        WHEN v IN ('표고', '표고버섯', '생표고버섯') THEN '표고버섯'
        WHEN v IN ('새송이', '새송이버섯') THEN '새송이버섯'
        WHEN v IN ('느타리', '느타리버섯') THEN '느타리버섯'
        WHEN v IN ('팽이', '팽이버섯') THEN '팽이버섯'
        WHEN v IN ('양송이', '양송이버섯') THEN '양송이버섯'

        -- 육류/해산물: 부위 차이가 큰 것은 최대한 보존
        WHEN v IN ('소고기', '쇠고기', '다진소고기', '다진쇠고기', '소고기다짐육', '쇠고기다짐육') THEN '소고기'
        WHEN v IN ('돼지고기', '돈육', '다진돼지고기', '돼지고기다짐육', '돼지다짐육') THEN '돼지고기'
        WHEN v IN ('닭고기', '닭', '닭정육') THEN '닭고기'
        WHEN v IN ('오징어', '오징어몸통') THEN '오징어'
        WHEN v IN ('새우', '칵테일새우', '냉동새우') THEN '새우'
        WHEN v IN ('멸치', '국물멸치', '다시멸치') THEN '멸치'
        WHEN v IN ('건새우', '마른새우') THEN '건새우'

        -- 콩/두부/유제품
        WHEN v IN ('두부', '부침두부', '찌개두부', '찌개용두부', '부침용두부') THEN '두부'
        WHEN v IN ('모짜렐라치즈', '모차렐라치즈', '피자치즈') THEN '모짜렐라치즈'
        WHEN v IN ('우유', '흰우유') THEN '우유'
        WHEN v IN ('버터', '무염버터', '가염버터') THEN '버터'

        -- 곡류/면/기타
        WHEN v IN ('밥', '흰밥', '공기밥') THEN '밥'
        WHEN v IN ('떡', '떡볶이떡', '떡국떡') THEN '떡'
        WHEN v IN ('라면사리', '라면') THEN '라면'
        WHEN v IN ('빵가루', '생빵가루') THEN '빵가루'
        WHEN v IN ('김', '구운김', '조미김') THEN '김'
        WHEN v IN ('김치', '배추김치', '익은김치', '신김치') THEN '김치'

        ELSE v
    END;

    -- 최종 방어: 너무 넓은 단일어로 과통합되는 경우는 원문 정리값으로 복구
    -- 단, 사용자가 명시한 '파 -> 대파' alias는 위에서 이미 처리된다.
    IF v IN ('장', '가루') THEN
        v := regexp_replace(raw, '\s+', '', 'g');
    END IF;

    RETURN NULLIF(v, '');
END;
$$;

-- 1~4. 각 행별 정규화 결과를 preview 테이블로 만든다.
CREATE TEMP TABLE tmp_ing_normalization_preview AS
SELECT
    ingredient_id,
    canonical_name AS old_canonical_name,
    normalized_name AS old_normalized_name,
    pg_temp.normalize_today_fridge_ingredient_name(
        COALESCE(NULLIF(normalized_name, ''), canonical_name)
    ) AS new_normalized_name
FROM today_fridge.ingredient_master;

-- 정규화 전/후 변경 미리보기
SELECT
    'changed_normalized_name_count' AS metric,
    COUNT(*) AS value
FROM tmp_ing_normalization_preview
WHERE old_normalized_name IS DISTINCT FROM new_normalized_name;

-- 1~4. normalized_name 업데이트
UPDATE today_fridge.ingredient_master im
SET normalized_name = p.new_normalized_name
FROM tmp_ing_normalization_preview p
WHERE im.ingredient_id = p.ingredient_id
  AND p.new_normalized_name IS NOT NULL
  AND im.normalized_name IS DISTINCT FROM p.new_normalized_name;

-- 5. 100% 겹치는 normalized_name 기준 병합 맵 생성
CREATE TEMP TABLE tmp_ing_merge_map AS
SELECT
    ingredient_id AS old_id,
    MIN(ingredient_id) OVER (PARTITION BY normalized_name) AS keep_id,
    normalized_name
FROM today_fridge.ingredient_master
WHERE normalized_name IS NOT NULL
  AND normalized_name <> '';

-- 병합 대상 수 확인
SELECT
    'merge_target_ingredient_master_rows' AS metric,
    COUNT(*) AS value
FROM tmp_ing_merge_map
WHERE old_id <> keep_id;

-- 병합 전, 대표적으로 어떤 이름들이 합쳐질지 확인
SELECT
    normalized_name,
    COUNT(*) AS row_count,
    ARRAY_AGG(old_id ORDER BY old_id) AS ingredient_ids
FROM tmp_ing_merge_map
GROUP BY normalized_name
HAVING COUNT(*) > 1
ORDER BY row_count DESC, normalized_name
LIMIT 100;

-- recipe_ingredient는 recipe_id + keep_id 기준 중복 가능성이 있으므로 FK 업데이트 전에 중복을 먼저 줄인다.
DO $$
BEGIN
    IF to_regclass('today_fridge.recipe_ingredient') IS NOT NULL
       AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'today_fridge'
              AND table_name = 'recipe_ingredient'
              AND column_name = 'recipe_id'
       )
       AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'today_fridge'
              AND table_name = 'recipe_ingredient'
              AND column_name = 'ingredient_master_id'
       )
    THEN
        DELETE FROM today_fridge.recipe_ingredient ri
        USING (
            SELECT ctid
            FROM (
                SELECT
                    ri.ctid,
                    ROW_NUMBER() OVER (
                        PARTITION BY ri.recipe_id, m.keep_id
                        ORDER BY
                            CASE WHEN ri.ingredient_master_id = m.keep_id THEN 0 ELSE 1 END,
                            ri.ctid
                    ) AS rn
                FROM today_fridge.recipe_ingredient ri
                JOIN tmp_ing_merge_map m
                  ON ri.ingredient_master_id = m.old_id
            ) d
            WHERE d.rn > 1
        ) dup
        WHERE ri.ctid = dup.ctid;

        UPDATE today_fridge.recipe_ingredient ri
        SET ingredient_master_id = m.keep_id
        FROM tmp_ing_merge_map m
        WHERE ri.ingredient_master_id = m.old_id
          AND m.old_id <> m.keep_id;
    END IF;
END $$;

-- user_ingredient도 user_id + keep_id 기준 중복 가능성이 있으므로 가능한 경우 먼저 줄인다.
DO $$
BEGIN
    IF to_regclass('today_fridge.user_ingredient') IS NOT NULL
       AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'today_fridge'
              AND table_name = 'user_ingredient'
              AND column_name = 'ingredient_master_id'
       )
    THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'today_fridge'
              AND table_name = 'user_ingredient'
              AND column_name = 'user_id'
        ) THEN
            DELETE FROM today_fridge.user_ingredient ui
            USING (
                SELECT ctid
                FROM (
                    SELECT
                        ui.ctid,
                        ROW_NUMBER() OVER (
                            PARTITION BY ui.user_id, m.keep_id
                            ORDER BY
                                CASE WHEN ui.ingredient_master_id = m.keep_id THEN 0 ELSE 1 END,
                                ui.ctid
                        ) AS rn
                    FROM today_fridge.user_ingredient ui
                    JOIN tmp_ing_merge_map m
                      ON ui.ingredient_master_id = m.old_id
                ) d
                WHERE d.rn > 1
            ) dup
            WHERE ui.ctid = dup.ctid;
        END IF;

        UPDATE today_fridge.user_ingredient ui
        SET ingredient_master_id = m.keep_id
        FROM tmp_ing_merge_map m
        WHERE ui.ingredient_master_id = m.old_id
          AND m.old_id <> m.keep_id;
    END IF;
END $$;

-- shopping_item_mcp FK 이동
DO $$
BEGIN
    IF to_regclass('today_fridge.shopping_item_mcp') IS NOT NULL
       AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'today_fridge'
              AND table_name = 'shopping_item_mcp'
              AND column_name = 'ingredient_master_id'
       )
    THEN
        UPDATE today_fridge.shopping_item_mcp sm
        SET ingredient_master_id = m.keep_id
        FROM tmp_ing_merge_map m
        WHERE sm.ingredient_master_id = m.old_id
          AND m.old_id <> m.keep_id;
    END IF;
END $$;

-- substitute_graph는 base/sub 양쪽이 합쳐질 수 있으므로 먼저 예정 중복을 줄이고 FK를 이동한다.
DO $$
BEGIN
    IF to_regclass('today_fridge.substitute_graph') IS NOT NULL
       AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'today_fridge'
              AND table_name = 'substitute_graph'
              AND column_name = 'base_ingredient_id'
       )
       AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'today_fridge'
              AND table_name = 'substitute_graph'
              AND column_name = 'sub_ingredient_id'
       )
    THEN
        -- cooking_context 컬럼이 있을 때의 중복 제거
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'today_fridge'
              AND table_name = 'substitute_graph'
              AND column_name = 'cooking_context'
        ) THEN
            DELETE FROM today_fridge.substitute_graph sg
            USING (
                SELECT ctid
                FROM (
                    SELECT
                        sg.ctid,
                        ROW_NUMBER() OVER (
                            PARTITION BY mb.keep_id, ms.keep_id, sg.cooking_context
                            ORDER BY sg.ctid
                        ) AS rn
                    FROM today_fridge.substitute_graph sg
                    JOIN tmp_ing_merge_map mb
                      ON sg.base_ingredient_id = mb.old_id
                    JOIN tmp_ing_merge_map ms
                      ON sg.sub_ingredient_id = ms.old_id
                ) d
                WHERE d.rn > 1
            ) dup
            WHERE sg.ctid = dup.ctid;
        ELSE
            DELETE FROM today_fridge.substitute_graph sg
            USING (
                SELECT ctid
                FROM (
                    SELECT
                        sg.ctid,
                        ROW_NUMBER() OVER (
                            PARTITION BY mb.keep_id, ms.keep_id
                            ORDER BY sg.ctid
                        ) AS rn
                    FROM today_fridge.substitute_graph sg
                    JOIN tmp_ing_merge_map mb
                      ON sg.base_ingredient_id = mb.old_id
                    JOIN tmp_ing_merge_map ms
                      ON sg.sub_ingredient_id = ms.old_id
                ) d
                WHERE d.rn > 1
            ) dup
            WHERE sg.ctid = dup.ctid;
        END IF;

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

        -- 자기 자신으로 대체하는 관계가 생기면 제거
        DELETE FROM today_fridge.substitute_graph
        WHERE base_ingredient_id = sub_ingredient_id;

        -- FK 이동 후 남은 중복 제거
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'today_fridge'
              AND table_name = 'substitute_graph'
              AND column_name = 'cooking_context'
        ) THEN
            DELETE FROM today_fridge.substitute_graph sg
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
            WHERE sg.ctid = dup.ctid;
        ELSE
            DELETE FROM today_fridge.substitute_graph sg
            USING (
                SELECT ctid
                FROM (
                    SELECT
                        ctid,
                        ROW_NUMBER() OVER (
                            PARTITION BY base_ingredient_id, sub_ingredient_id
                            ORDER BY ctid
                        ) AS rn
                    FROM today_fridge.substitute_graph
                ) d
                WHERE d.rn > 1
            ) dup
            WHERE sg.ctid = dup.ctid;
        END IF;
    END IF;
END $$;

-- 5. FK를 모두 옮긴 뒤 중복 ingredient_master 삭제
DELETE FROM today_fridge.ingredient_master im
USING tmp_ing_merge_map m
WHERE im.ingredient_id = m.old_id
  AND m.old_id <> m.keep_id;

-- 최종 결과 확인
SELECT
    'before_ingredient_master_rows' AS metric,
    ingredient_master_rows AS value
FROM tmp_ing_before_counts
UNION ALL
SELECT
    'before_distinct_normalized_names' AS metric,
    distinct_normalized_names AS value
FROM tmp_ing_before_counts
UNION ALL
SELECT
    'after_ingredient_master_rows' AS metric,
    COUNT(*) AS value
FROM today_fridge.ingredient_master
UNION ALL
SELECT
    'after_distinct_normalized_names' AS metric,
    COUNT(DISTINCT normalized_name) FILTER (
        WHERE normalized_name IS NOT NULL AND normalized_name <> ''
    ) AS value
FROM today_fridge.ingredient_master;

-- 남은 중복 그룹 확인
SELECT
    normalized_name,
    COUNT(*) AS cnt,
    ARRAY_AGG(ingredient_id ORDER BY ingredient_id) AS ids
FROM today_fridge.ingredient_master
WHERE normalized_name IS NOT NULL
  AND normalized_name <> ''
GROUP BY normalized_name
HAVING COUNT(*) > 1
ORDER BY cnt DESC, normalized_name
LIMIT 50;

COMMIT;
