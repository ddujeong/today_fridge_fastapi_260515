# tests/crawler/test_del_deduplicated_recipes.py
import unittest
from unittest.mock import MagicMock, patch, call
import sys
from pathlib import Path

# 스크립트가 실행 가능한 경로에 있도록 설정 (실제 환경에 따라 조정 필요)
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.crawler.del_deduplicated_recipes import find_and_delete_duplicates

class TestDelDeduplicatedRecipes(unittest.TestCase):

    def setUp(self):
        # Mock 객체 생성
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.execute.return_value = self.mock_cursor
        self.mock_conn.__enter__.return_value = self.mock_conn
        
        self.db_url = "postgresql://user:pass@localhost:5432/db"
        self.schema = "test_schema"

    @patch("psycopg.connect")
    @patch("app.crawler.del_deduplicated_recipes.get_tables")
    @patch("app.crawler.del_deduplicated_recipes.DbMeta")
    def test_no_duplicates_found(self, MockDbMeta, mock_get_tables, mock_connect):
        """중복 레시피가 없을 때 아무것도 삭제하지 않아야 함을 테스트"""
        mock_connect.return_value = self.mock_conn
        mock_get_tables.return_value = {"recipes", "recipe_ingredient", "recipe_step"}
        
        # Mock Meta 설정
        instance = MockDbMeta.return_value
        instance.pk.return_value = "id"
        instance.pick.side_effect = lambda table, candidates, required=False: (
            "source_site" if "source_site" in candidates else 
            "source_recipe_key" if "source_recipe_key" in candidates else 
            "title" if "title" in candidates else None
        )
        instance.get_timestamp_column.return_value = "created_at"
        instance.has.return_value = True
        instance.columns.return_value = {"id", "source_site", "source_recipe_key", "title", "created_at"}

        # 데이터: 중복 없는 단일 레시피 1개
        # row format: (id, source_site, group_key, keep_value)
        self.mock_cursor.fetchall.return_value = [(1, "site_a", "key_a", "2023-01-01")]

        find_and_delete_duplicates(self.db_url, self.schema, dry_run=False)

        # 삭제 쿼리가 호출되지 않았는지 확인
        # DELETE FROM recipes 문이 실행되지 않아야 함
        for call_args in self.mock_conn.execute.call_args_list:
            query = call_args[0][0]
            self.assertNotIn("DELETE FROM", str(query))

    @patch("psycopg.connect")
    @patch("app.crawler.del_deduplicated_recipes.get_tables")
    @patch("app.crawler.del_deduplicated_recipes.DbMeta")
    def test_delete_duplicates_logic(self, MockDbMeta, mock_get_tables, mock_connect):
        """중복 레시피가 있을 때 가장 오래된 것만 남기고 삭제하는지 테스트"""
        mock_connect.return_value = self.mock_conn
        mock_get_tables.return_value = {"recipes", "recipe_ingredient", "recipe_step"}
        
        instance = MockDbMeta.return_value
        instance.pk.return_value = "id"
        instance.pick.side_effect = lambda table, candidates, required=False: (
            "source_site" if "source_site" in candidates else 
            "source_recipe_key" if "source_recipe_key" in candidates else 
            "title" if "title" in candidates else None
        )
        instance.get_timestamp_column.return_value = "created_at"
        instance.columns.return_value = {"id", "source_site", "source_recipe_key", "title", "created_at"}

        # 데이터: 
        # ID 1: site_a, key_a, 2023-01-01 (남길 것)
        # ID 2: site_a, key_a, 2023-02-01 (삭제할 것)
        # ID 3: site_b, key_b, 2023-01-01 (단독 - 남길 것)
        self.mock_cursor.fetchall.return_value = [
            (1, "site_a", "key_a", "2023-01-01"),
            (2, "site_a", "key_a", "2023-02-01"),
            (3, "site_b", "key_b", "2023-01-01"),
        ]

        find_and_delete_duplicates(self.db_url, self.schema, dry_run=False)

        # 삭제 쿼리 확인
        # 2번 ID가 삭제되어야 함
        delete_calls = [
            call for call in self.mock_conn.execute.call_args_list 
            if "DELETE FROM" in str(call[0][0]) and "recipes" in str(call[0][0])
        ]
        self.assertEqual(len(delete_calls), 1)
        self.assertEqual(delete_calls[0][0][1], (2,))

    @patch("psycopg.connect")
    @patch("app.crawler.del_deduplicated_recipes.get_tables")
    @patch("app.crawler.del_deduplicated_recipes.DbMeta")
    def test_dry_run_mode(self, MockDbMeta, mock_get_tables, mock_connect):
        """Dry Run 모드일 때는 실제 DELETE 쿼리가 실행되지 않아야 함을 테스트"""
        mock_connect.return_value = self.mock_conn
        mock_get_tables.return_value = {"recipes"}
        
        instance = MockDbMeta.return_value
        instance.pk.return_value = "id"
        instance.pick.side_effect = lambda table, candidates, required=False: "title"
        instance.get_timestamp_column.return_value = None
        instance.columns.return_value = {"id", "title"}

        # 중복 데이터
        self.mock_cursor.fetchall.return_value = [
            (1, "site_a", "key_a", 1),
            (2, "site_a", "key_a", 2),
        ]

        find_and_delete_duplicates(self.db_url, self.schema, dry_run=True)

        # DELETE 쿼리가 실행되지 않아야 함
        for call_args in self.mock_conn.execute.call_args_list:
            query = call_args[0][0]
            self.assertNotIn("DELETE FROM", str(query))

if __name__ == "__main__":
    unittest.main() 