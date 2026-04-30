import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


current_file = Path(__file__).resolve()
project_root = current_file.parents[3]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from app.api.IngredientClassifier import ingredientRouter


class TestIngredientRouter:
    @pytest.fixture
    def mock_classifier(self):
        # ingredientRouter.py는 import 시점에 classifier 인스턴스를 생성하므로
        # 클래스가 아니라 모듈 전역 classifier를 직접 patch해야 한다.
        with patch.object(ingredientRouter, "classifier", MagicMock()) as mock_obj:
            yield mock_obj

    @pytest.fixture
    def client(self):
        # 라우터에서 예외를 처리하지 않으므로 500 응답을 검증할 수 있게 설정
        return TestClient(ingredientRouter.app, raise_server_exceptions=False)

    def test_classify_image_success(self, client, mock_classifier):
        mock_response = {
            "status": "success",
            "class": "Tomato",
            "confidence": 0.95,
        }
        mock_classifier.classify_image.return_value = mock_response
        test_image_path = "test_images/tomato.jpg"

        response = client.post(
            "/vision/ingredient-route",
            params={"image_path": test_image_path},
        )

        assert response.status_code == 200
        assert response.json() == mock_response
        mock_classifier.classify_image.assert_called_once_with(test_image_path)

    def test_classify_image_file_not_found(self, client, mock_classifier):
        mock_classifier.classify_image.side_effect = FileNotFoundError("File not found")

        response = client.post(
            "/vision/ingredient-route",
            params={"image_path": "invalid/path.jpg"},
        )

        assert response.status_code == 500

    def test_classify_image_invalid_format(self, client, mock_classifier):
        mock_classifier.classify_image.side_effect = ValueError("Unsupported format")

        response = client.post(
            "/vision/ingredient-route",
            params={"image_path": "test_images/text_file.txt"},
        )

        assert response.status_code == 500
