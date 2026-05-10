# 이 파일은 psycopg2를 사용하여 데이터베이스 연결을 관리하는 설정 파일입니다.
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# 데이터베이스 연결 URL을 가져옵니다.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError(".env에 DATABASE_URL을 설정해주세요.")

# 데이터베이스 연결을 가져오기 위한 의존성 주입용 함수입니다.
def get_db():
    """
    psycopg2 연결을 생성하고 DictCursor를 반환합니다.
    """
    conn = psycopg2.connect(DATABASE_URL)
    try:
        # RealDictCursor를 사용하여 결과를 dict 형태로 받습니다.
        cur = conn.cursor(cursor_factory=RealDictCursor)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
