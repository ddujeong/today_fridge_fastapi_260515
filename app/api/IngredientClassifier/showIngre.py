# showIngre.py
import psycopg2
import os

UPGRADED_MODE = True  # 또는 False로 설정 가능

print(f"Upgraded Mode: {UPGRADED_MODE}")  # 디버깅용 출력 추가

def export_ingredients():
    conn = None
    try:
        # DB 정보 (실제 환경에 맞게 수정됨)
        DB_CONFIG = {
            "user": "postgres",
            "password": "1234",  # 공백 제거
            "host": "localhost",
            "port": "5432",
            "dbname": "today_fridge"
        }
        
        TABLE_NAME = "today_fridge.ingredient_master"       # 스키마 포함 테이블 이름
        COLUMN_NAME = "canonical_name"   # 재료 이름이 저장된 컬럼 이름
        OUTPUT_FILE = "ingredients_list.txt"

        # 1. DB 연결
        print(f"Connecting to database '{DB_CONFIG['dbname']}'...")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # 2. 데이터 조회 쿼리 실행
        query = f"SELECT {COLUMN_NAME} FROM {TABLE_NAME};"
        cur.execute(query)
        
        # 3. 모든 행 가져오기
        rows = cur.fetchall()

        if not rows:
            print("No ingredients found in the table.")
            return

        # 4. 텍스트 파일로 저장 (개행으로 분리)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for row in rows:
                ingredient = row[0]
                if ingredient:
                    f.write(f"{ingredient}\n")

        print(f"✅ Success! {len(rows)} ingredients saved to '{OUTPUT_FILE}'.")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    if UPGRADED_MODE:
        export_ingredients()
    else:
        # 업그레이드 모드가 아닐 때 실행될 코드
        print("Running in Normal Mode")
