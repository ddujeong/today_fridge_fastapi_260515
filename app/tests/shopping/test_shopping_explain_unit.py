"""
단위 테스트: 쇼핑 추천 이유 설명 서비스

UT-SHOP-001  build_prompt — 레시피 컨텍스트 있음
UT-SHOP-002  build_prompt — 레시피 컨텍스트 없음 (가격·배송 정보만)
UT-SHOP-003  build_prompt — 할인 정보 포함
UT-SHOP-004  build_prompt — shoppingItems 없고 lowestPrice만 있을 때
UT-SHOP-005  generate_shopping_explanation — ollama 성공 경로
UT-SHOP-006  generate_shopping_explanation — ollama 실패 시 gemini 폴백
UT-SHOP-007  ShoppingExplainRequest 스키마 — 필수 필드 / 선택 필드 기본값
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.schemas.shopping_explain_schema import (
    ShoppingExplainRequest,
    ShoppingExplainResponse,
    ShoppingItemInfo,
)
from app.services.shopping_explanation_service import (
    build_prompt,
    generate_shopping_explanation,
)


# ── 픽스처 ────────────────────────────────────────────────────────────────────

def _make_item(
    mall: str = "네이버쇼핑",
    name: str = "풀무원 두부 300g",
    price: int = 1_980,
    shipping: str = "FREE",
    original_price: int | None = None,
    discount: int | None = None,
) -> ShoppingItemInfo:
    return ShoppingItemInfo(
        mallName=mall,
        productName=name,
        price=price,
        shippingType=shipping,
        originalPrice=original_price,
        discountRate=discount,
    )


def _make_request(**kwargs) -> ShoppingExplainRequest:
    defaults = dict(
        ingredientName="두부",
        shoppingItems=[_make_item()],
        lowestPrice=1_980,
    )
    defaults.update(kwargs)
    return ShoppingExplainRequest(**defaults)


# ── UT-SHOP-001 ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_ut_shop_001_build_prompt_with_recipe_context() -> None:
    """레시피 컨텍스트가 있으면 프롬프트에 레시피명·재료가 포함돼야 한다."""
    req = _make_request(
        recipeTitle="순두부찌개",
        matchedIngredients=["고추장", "다진마늘"],
    )
    prompt = build_prompt(req)

    assert "순두부찌개" in prompt
    assert "두부" in prompt
    assert "고추장" in prompt
    # 레시피 컨텍스트 분기 프롬프트 키워드 확인
    assert "레시피" in prompt


# ── UT-SHOP-002 ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_ut_shop_002_build_prompt_without_recipe_context() -> None:
    """레시피 컨텍스트가 없으면 가격·배송 중심 프롬프트가 생성돼야 한다."""
    req = _make_request()  # recipeTitle=None
    prompt = build_prompt(req)

    assert "두부" in prompt
    assert "1,980원" in prompt
    assert "무료배송" in prompt
    # 레시피 분기로 들어가지 않았는지 확인
    assert "레시피명" not in prompt


# ── UT-SHOP-003 ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_ut_shop_003_build_prompt_includes_discount_info() -> None:
    """할인율이 있으면 프롬프트에 '% 할인' 문구가 포함돼야 한다."""
    item = _make_item(original_price=2_500, discount=20)
    req = _make_request(shoppingItems=[item])
    prompt = build_prompt(req)

    assert "20% 할인" in prompt


# ── UT-SHOP-004 ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_ut_shop_004_build_prompt_lowest_price_fallback() -> None:
    """shoppingItems가 없고 lowestPrice만 있으면 최저가 문구가 포함돼야 한다."""
    req = _make_request(shoppingItems=[], lowestPrice=1_500)
    prompt = build_prompt(req)

    assert "1,500원" in prompt


# ── UT-SHOP-005 ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_ut_shop_005_generate_uses_ollama_when_available() -> None:
    """ollama가 정상 응답하면 그 결과를 반환해야 한다."""
    req = _make_request()
    expected = "네이버쇼핑에서 무료배송으로 저렴하게 구매할 수 있는 두부입니다."

    with patch(
        "app.services.shopping_explanation_service.ollama.generate",
        return_value=expected,
    ):
        result = generate_shopping_explanation(req)

    assert isinstance(result, ShoppingExplainResponse)
    assert result.explanation == expected


# ── UT-SHOP-006 ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_ut_shop_006_generate_falls_back_to_gemini_on_ollama_error() -> None:
    """ollama 호출이 실패하면 gemini로 폴백해야 한다."""
    req = _make_request()
    gemini_answer = "Gemini가 대신 생성한 추천 이유입니다."

    with (
        patch(
            "app.services.shopping_explanation_service.ollama.generate",
            side_effect=RuntimeError("ollama 연결 실패"),
        ),
        patch(
            "app.services.shopping_explanation_service.gemini.generate",
            return_value=gemini_answer,
        ),
    ):
        result = generate_shopping_explanation(req)

    assert result.explanation == gemini_answer


# ── UT-SHOP-007 ────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_ut_shop_007_schema_defaults_and_required_field() -> None:
    """필수 필드(ingredientName)만으로 요청을 만들 수 있고, 선택 필드는 기본값을 가진다."""
    req = ShoppingExplainRequest(ingredientName="계란")

    assert req.ingredientName == "계란"
    assert req.recipeTitle is None
    assert req.recipeId is None
    assert req.matchedIngredients == []
    assert req.missingIngredients == []
    assert req.shoppingItems == []
    assert req.lowestPrice is None
