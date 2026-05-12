from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_create_embedding_success(monkeypatch):
    # mock: 실제 embedding 모델 호출 제거
    def mock_generate_embedding(text: str):
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(
    "app.api.routes.embedding.generate_embedding",
    mock_generate_embedding
    )

    # API 호출
    response = client.post("/api/v1/embedding", json={
        "text": "김치찌개"
    })

    # 검증
    assert response.status_code == 200

    data = response.json()

    assert data["dimension"] == 3
    assert isinstance(data["embedding"], list)
    assert len(data["embedding"]) == 3


def test_create_embedding_validation_error():
    # text 필드 없음 → validation 에러
    response = client.post("/api/v1/embedding", json={})

    assert response.status_code == 422