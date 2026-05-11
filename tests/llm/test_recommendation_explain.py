from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_explain_recommendation_success(monkeypatch):
    # mock service
    def mock_generate(request):
        return {
            "explanation": "저염식 추천입니다."
        }

    monkeypatch.setattr(
    "app.api.routes.recommendation_llm.generate_recommendation_explanation",
    mock_generate
    )

    response = client.post(
        "/api/v1/internal/llm/recommendation/explain",
        json={
            "recipeId": 1,
            "title": "김치찌개",
            "matchedIngredients": ["김치"],
            "missingIngredients": ["두부"],
            "conditionTags": ["LOW_SODIUM"],
            "matchRate": 80.0,
            "totalScore": 75.0,
            "semanticScore": 0.8,
            "hybridScore": 78.0,
            "reason": "저염식 추천"
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert "explanation" in data

def test_explain_recommendation_validation_error():
    # 잘못된 요청
    response = client.post(
        "/api/v1/internal/llm/recommendation/explain",
        json={}
    )

    assert response.status_code == 422