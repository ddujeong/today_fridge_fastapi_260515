### 의존성 설치
루트폴더에서 pip install -r requirements.txt로 의존성 다운로드

### 크롤러 실행법
Crawler_main.py에서 page를 원하는 페이지에 두고 f5눌러서 실행

### 레시피 db 적재법
아래 명령어 터미널에서 실행
python app/crawler/import_recipe_csvs_to_postgres_v3.py \
--input app/crawler/recipes_result/ \
--db-url "postgresql://postgres:1234@localhost:5432/today_fridge" \
--schema "public" \
--source-site "MyCrawler" \
--allow-empty-steps \

## 식재료 정규화 넣는법
normalize.sql 실행 
PGPASSWORD=1234 psql -h localhost -p 5432 -U postgres -d today_fridge -f app/crawler/normalize.sql




### db에서 중복 레시피 삭제법
del_deduplicated_recipes.py 실행







## 1. 레시피 적재 
python app/crawler/import_recipe_csvs_to_postgres_v3.py \                                         
--input app/crawler/recipes_result/ \
--db-url "postgresql://postgres:1234@localhost:5432/today_fridge" \
--schema "today_fridge" \
--source-site "MyCrawler" \
--allow-empty-steps \

## 2. 재료 정규화 및 중복재료 통합
PGPASSWORD=1234 psql -h localhost -p 5432 -U postgres -d today_fridge -f app/crawler/normalize.sql