import pytest
from unittest.mock import patch, mock_open
from app.api.IngredientClassifier.showIngre import export_ingredients

def test_export_ingredients():
    # 모킹된 DB 설정 (동일한 값 사용)
    db_config = {
        "user": "postgres",
        "password": "1234",  # 실제 비밀번호와 일치해야 합니다.
        "host": "localhost",
        "port": "5432",
        "dbname": "today_fridge"
    }
    
    table_name = "today_fridge"
    column_name = "ingredient_name"
    output_file = "ingredients_list.txt"

    with patch('psycopg2.connect') as mock_connect:
        # 모킹된 커넥션 객체와 커서 객체 생성
        mock_conn = mock_connect.return_value
        mock_cursor = mock_conn.cursor.return_value
        
        # 예상 결과 데이터 설정
        mock_cursor.fetchall.return_value = [
            ("apple",),
            ("banana",),
            ("carrot",)
        ]

        # 테스트 실행
        export_ingredients()

        # 모킹된 메서드 호출 확인
        mock_connect.assert_called_once_with(**db_config)
        mock_cursor.execute.assert_called_once_with(f"SELECT {column_name} FROM {table_name};")
        mock_cursor.fetchall.assert_called_once()
        mock_conn.close.assert_called_once()

        # 생성된 파일 내용 검증
        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read().strip().split('\n')
        
        assert content == ["apple", "banana", "carrot"]

def test_export_ingredients_no_data():
    # 모킹된 DB 설정 (동일한 값 사용)
    db_config = {
        "user": "postgres",
        "password": "1234",  # 실제 비밀번호와 일치해야 합니다.
        "host": "localhost",
        "port": "5432",
        "dbname": "today_fridge"
    }
    
    table_name = "today_fridge"
    column_name = "ingredient_name"
    output_file = "ingredients_list.txt"

    with patch('psycopg2.connect') as mock_connect:
        # 모킹된 커넥션 객체와 커서 객체 생성
        mock_conn = mock_connect.return_value
        mock_cursor = mock_conn.cursor.return_value
        
        # 예상 결과 데이터 설정 (데이터 없음)
        mock_cursor.fetchall.return_value = []

        # 테스트 실행
        export_ingredients()

        # 모킹된 메서드 호출 확인
        mock_connect.assert_called_once_with(**db_config)
        mock_cursor.execute.assert_called_once_with(f"SELECT {column_name} FROM {table_name};")
        mock_cursor.fetchall.assert_called_once()
        mock_conn.close.assert_called_once()

        # 생성된 파일 내용 검증 (파일이 비어있음)
        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        assert content == ""

def test_export_ingredients_exception():
    # 모킹된 DB 설정 (동일한 값 사용)
    db_config = {
        "user": "postgres",
        "password": "1234",  # 실제 비밀번호와 일치해야 합니다.
        "host": "localhost",
        "port": "5432",
        "dbname": "today_fridge"
    }
    
    table_name = "today_fridge"
    column_name = "ingredient_name"
    output_file = "ingredients_list.txt"

    with patch('psycopg2.connect') as mock_connect:
        # 모킹된 커넥션 객체와 커서 객체 생성
        mock_conn = mock_connect.return_value
        mock_cursor = mock_conn.cursor.return_value
        
        # 예외 발생 설정
        mock_cursor.execute.side_effect = Exception("Database error")

        # 테스트 실행 및 예외 검증
        with pytest.raises(Exception) as context:
            export_ingredients()
        
        assert "❌ Error: Database error" in str(context.value)
