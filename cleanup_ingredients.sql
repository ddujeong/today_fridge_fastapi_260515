-- 종합 식재료 정규화 스크립트 (V3)
-- 1. 영문 재료 삭제 (참조 데이터 포함)
-- 2. 줄바꿈(\n) 이후 내용 제거
-- 3. '고운', '가는', '갈은' 키워드 제거
-- 4. 모든 띄어쓰기 제거 및 통합
BEGIN;

-- A. 영문 재료 삭제를 위한 임시 테이블 생성
CREATE TEMP TABLE tmp_en_ids AS
SELECT ingredient_id FROM today_fridge.ingredient_master 
WHERE normalized_name ~ '^[a-zA-Z0-9\s\-_,\(\)\/\n\.]+$';

-- 참조 데이터 삭제
DELETE FROM today_fridge.user_ingredient WHERE ingredient_master_id IN (SELECT ingredient_id FROM tmp_en_ids);
DELETE FROM today_fridge.recipe_ingredient WHERE ingredient_master_id IN (SELECT ingredient_id FROM tmp_en_ids);
DELETE FROM today_fridge.ingredient_master WHERE ingredient_id IN (SELECT ingredient_id FROM tmp_en_ids);


-- B. 정규화 함수 생성 (줄바꿈 제거 + 키워드 제거 + 띄어쓰기 제거)
CREATE OR REPLACE FUNCTION today_fridge.fn_normalize_name(name TEXT) RETURNS TEXT AS $$
DECLARE
    v_ret TEXT;
BEGIN
    -- 1. 첫 줄바꿈(\n) 이전의 내용만 취함
    v_ret := SPLIT_PART(name, E'\n', 1);
    -- 2. '고운', '가는', '갈은' 제거
    v_ret := REPLACE(v_ret, '고운', '');
    v_ret := REPLACE(v_ret, '가는', '');
    v_ret := REPLACE(v_ret, '갈은', '');
    -- 3. 모든 띄어쓰기 제거
    v_ret := REPLACE(v_ret, ' ', '');
    RETURN TRIM(v_ret);
END;
$$ LANGUAGE plpgsql;


-- C. 통합 처리
DO $$
DECLARE
    r RECORD;
    v_new_name TEXT;
    v_target_id BIGINT;
BEGIN
    FOR r IN 
        SELECT ingredient_id, normalized_name 
        FROM today_fridge.ingredient_master 
        WHERE normalized_name LIKE '%' || E'\n' || '%'
           OR normalized_name LIKE '%고운%' 
           OR normalized_name LIKE '%가는%' 
           OR normalized_name LIKE '%갈은%'
           OR normalized_name LIKE '% %' -- 띄어쓰기가 있는 경우 포함
    LOOP
        v_new_name := today_fridge.fn_normalize_name(r.normalized_name);
        
        -- 빈 문자열이 되었거나 변함이 없으면 스킵
        CONTINUE WHEN v_new_name = '' OR v_new_name = r.normalized_name;

        -- 동일한 이름을 가진 다른 마스터가 있는지 확인
        SELECT ingredient_id INTO v_target_id 
        FROM today_fridge.ingredient_master 
        WHERE normalized_name = v_new_name AND ingredient_id != r.ingredient_id 
        LIMIT 1;

        IF v_target_id IS NOT NULL THEN
            -- 이미 존재하면 참조만 옮기고 삭제
            UPDATE today_fridge.recipe_ingredient SET ingredient_master_id = v_target_id WHERE ingredient_master_id = r.ingredient_id;
            UPDATE today_fridge.user_ingredient SET ingredient_master_id = v_target_id WHERE ingredient_master_id = r.ingredient_id;
            DELETE FROM today_fridge.ingredient_master WHERE ingredient_id = r.ingredient_id;
        ELSE
            -- 존재하지 않으면 이름만 변경
            UPDATE today_fridge.ingredient_master SET normalized_name = v_new_name WHERE ingredient_id = r.ingredient_id;
        END IF;
    END LOOP;
END $$;

DROP FUNCTION today_fridge.fn_normalize_name(TEXT);

COMMIT;
