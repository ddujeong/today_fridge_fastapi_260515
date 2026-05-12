"""
E2E 테스트: POST /api/v1/internal/llm/shopping/explain

E2E-SHOP-001  레시피 컨텍스트 포함 전체 요청 → 200 + explanation 반환
E2E-SHOP-002  최소 요청 (ingredientName + shoppingItems만) → 200 + explanation 반환
E2E-SHOP-003  shoppingItems 없이 lowestPrice만 → 200 + explanation 반환
E2E-SHOP-004  ingredientName 누락 → 422 Unprocessable Entity
E2E-SHOP-005  ollama 장애 시 gemini 폴백으로 200 반환
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.shopping_explain import router


# ── 공통 픽스처 ────────────────────────────────────────────────────────────────

FAKE_EXPLANATION = "테스트용 AI 추천 이유 문장입니다."

FULL_PAYLOAD = {
    "ingredientName": "두부",
    "recipeTitle": "순두부찌개",
    "recipeId": 42,
    "matchedIngredients": ["고추장", "다진마늘"],
    "missingIngredients": ["두부"],
    "shoppingItems": [
        {
            "mallName": "네이버쇼핑",
            "productName": "풀무원 국산콩 두부 300g",
            "price": 1980,
            "shippingType": "FREE",
            "originalPrice": 2500,
            "discountRate": 20,
        },
        {
            "mallName": "11번가",
            "productName": "CJ 행복한콩 두부 350g",
            "price": 2100,
            "shippingType": "STANDARD",
        },
    ],
    "lowestPrice": 1980,
}


@pytest.fixture()
def client() -> TestClient:
    """LLM 서비스를 mock 처리한 TestClient."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    with (
        patch(
            "app.services.shopping_explanation_service.ollama.generate",
            return_value=FAKE_EXPLANATION,
        ),
        patch(
            "app.services.shopping_explanation_service.gemini.generate",
            return_value=FAKE_EXPLANATION,
        ),
    ):
        with TestClient(app) as c:
            yield c


URL = "/api/v1/internal/llm/shopping/explain"


# ── E2E-SHOP-001 ───────────────────────────────────────────────────────────────

@pytest.mark.e2e
def test_e2e_shop_001_full_request_returns_explanation(client: TestClient) -> None:
    """레시피 컨텍스트를 포함한 전체 요청에서 200과 explanation 필드를 반환해야 한다."""
    response = client.post(URL, json=FULL_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert "explanation" in body
    assert isinstance(body["explanation"], str)
    assert len(body["explanation"]) > 0


# ── E2E-SHOP-002 ───────────────────────────────────────────────────────────────

@pytest.mark.e2e
def test_e2e_shop_002_minimal_request(client: TestClient) -> None:
    """ingredientName + shoppingItems만으로도 200을 반환해야 한다."""
    payload = {
        "ingredientName": "계란",
        "shoppingItems": [
            {
                "mallName": "네이버쇼핑",
                "productName": "신선한 계란 30구",
                "price": 5900,
                "shippingType": "FREE",
            }
        ],
    }
    response = client.post(URL, json=payload)

    assert response.status_code == 200
    assert "explanation" in response.json()


# ── E2E-SHOP-003 ───────────────────────────────────────────────────────────────

@pytest.mark.e2e
def test_e2e_shop_003_lowest_price_only(client: TestClient) -> None:
    """shoppingItems 없이 lowestPrice만 있어도 200을 반환해야 한다."""
    payload = {
        "ingredientName": "대파",
        "lowestPrice": 890,
    }
    response = client.post(URL, json=payload)

    assert response.status_code == 200
    assert "explanation" in response.json()


# ── E2E-SHOP-004 ───────────────────────────────────────────────────────────────

@pytest.mark.e2e
def test_e2e_shop_004_missing_required_field_returns_422(client: TestClient) -> None:
    """ingredientName이 없으면 422 Unprocessable Entity를 반환해야 한다."""
    payload = {
        "lowestPrice": 1000,
        "shoppingItems": [],
    }
    response = client.post(URL, json=payload)

    assert response.status_code == 422


# ── E2E-SHOP-005 ───────────────────────────────────────────────────────────────

@pytest.mark.e2e
def test_e2e_shop_005_ollama_failure_fallback_to_gemini() -> None:
    """ollama가 실패해도 gemini 폴백으로 200을 반환해야 한다."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    gemini_answer = "Gemini 폴백 추천 이유."

    with (
        patch(
            "app.services.shopping_explanation_service.ollama.generate",
            side_effect=RuntimeError("연결 거부"),
        ),
        patch(
            "app.services.shopping_explanation_service.gemini.generate",
            return_value=gemini_answer,
        ),
    ):
        with TestClient(app) as c:
            response = c.post(URL, json={"ingredientName": "양파", "lowestPrice": 500})

    assert response.status_code == 200
    assert response.json()["explanation"] == gemini_answer
