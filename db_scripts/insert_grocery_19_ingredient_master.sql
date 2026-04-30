-- Grocery coarse 폴더와 매핑되지만 normalize/sync 과정에서 빠졌을 수 있는 19종
-- COPY tmp_ingredient_master_sync ... 와 동일 컬럼·값 (사용자 제공 스냅샷 기준)
--
-- 실행 전: ingredient_id 충돌 여부 확인. 이미 있으면 DO NOTHING 또는 수동 조정.
--   psql -d today_fridge -f db_scripts/insert_grocery_19_ingredient_master.sql

BEGIN;

INSERT INTO today_fridge.ingredient_master (
  ingredient_id,
  category_id,
  canonical_name,
  normalized_name,
  alias_text,
  standard_unit,
  description,
  is_active,
  embedding,
  embedding_updated_at,
  created_at,
  updated_at
) VALUES
  (394, 3, 'Pear', '배', E'배, Pear', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.758643+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (395, 3, 'Avocado', '아보카도', E'아보카도, Avocado', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.767638+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (396, 3, 'Pomegranate', '석류', E'석류, Pomegranate', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.776633+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (397, 3, 'Kiwi', '키위', E'키위, Kiwi', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.784629+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (399, 3, 'Plum', '자두', E'자두, Plum', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.802618+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (400, 3, 'Nectarine', '천도복숭아', E'천도복숭아, Nectarine', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.810613+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (401, 3, 'Red-Grapefruit', '자몽', E'레드자몽, 자몽, Red-Grapefruit', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.819608+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (402, 3, 'Lime', '라임', E'라임, Lime', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.829603+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (403, 3, 'Mango', '망고', E'망고, Mango', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.837598+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (404, 3, 'Passion-Fruit', '패션프루트', E'패션프루트, Passion-Fruit', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.846593+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (405, 3, 'Banana', '바나나', E'바나나, Banana', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.854588+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (406, 3, 'Papaya', '파파야', E'파파야, Papaya', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.863583+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (407, 3, 'Satsumas', '귤', E'사츠마, 귤, Satsumas', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.872578+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (408, 3, 'Pineapple', '파인애플', E'파인애플, Pineapple', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.880573+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (409, 3, 'Melon', '멜론', E'멜론, Melon', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.889569+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (410, 3, 'Orange', '오렌지', E'오렌지, Orange', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.897276+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (411, 3, 'Peach', '복숭아', E'복숭아, Peach', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.905271+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (418, 2, 'Red-Beet', '비트', E'레드비트, 비트, Red-Beet', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.96572+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz),
  (421, 2, 'Ginger', '생강', E'생강, Ginger', 'g', NULL, TRUE, NULL, NULL, '2026-04-28 12:46:38.986707+09'::timestamptz, '2026-04-29 14:52:08.121089+09'::timestamptz)
ON CONFLICT (ingredient_id) DO NOTHING;

COMMIT;
