from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_classify_recipe_tags_success(monkeypatch):
    # mock LLM 응답
    def mock_generate(prompt: str):
        return """
        {
          "tags": [
            {"tagType":"COOKING_TYPE","tagCode":"SOUP","confidence":0.95},
            {"tagType":"STYLE","tagCode":"SPICY","confidence":0.8}
          ]
        }
        """

    monkeypatch.setattr(
        "app.api.routes.recipe_tag.gemini_service.generate",
        mock_generate
    )

    response = client.post("/api/v1/internal/recipe-tags/classify", json={
        "recipeId": 1,
        "title": "김치찌개",
        "ingredients": ["김치", "돼지고기"],
        "summary": "매콤한 찌개"
    })

    assert response.status_code == 200

    data = response.json()

    assert data["recipeId"] == 1
    assert len(data["tags"]) >= 1

    tag_types = [t["tagType"] for t in data["tags"]]

    assert "COOKING_TYPE" in tag_types or "STYLE" in tag_types


def test_classify_recipe_tags_invalid_llm_response(monkeypatch):
    # JSON 아닌 응답
    def mock_generate(prompt: str):
        return "이상한 응답입니다"

    monkeypatch.setattr(
        "app.api.routes.recipe_tag.gemini_service.generate",
        mock_generate
    )

    response = client.post("/api/v1/internal/recipe-tags/classify", json={
        "recipeId": 2,
        "title": "김치찌개"
    })

    assert response.status_code == 200

    data = response.json()

    # fallback 확인
    assert data["tags"] == []


def test_classify_recipe_tags_validation_error():
    # recipeId 없음
    response = client.post("/api/v1/internal/recipe-tags/classify", json={
        "title": "김치찌개"
    })

    assert response.status_code == 422
    
def test_validate_cooking_type_filter(monkeypatch):
    def mock_generate(prompt: str):
        return """
        {
          "tags": [
            {"tagType":"COOKING_TYPE","tagCode":"SOUP","confidence":0.9}
          ]
        }
        """

    monkeypatch.setattr(
        "app.api.routes.recipe_tag.gemini_service.generate",
        mock_generate
    )

    response = client.post("/api/v1/internal/recipe-tags/classify", json={
        "recipeId": 3,
        "title": "김치볶음밥"  # SOUP이면 안됨
    })

    data = response.json()

    # 필터링 되어야 정상
    assert data["tags"] == []