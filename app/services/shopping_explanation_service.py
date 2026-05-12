from app.schemas.shopping_explain_schema import (
    ShoppingExplainRequest,
    ShoppingExplainResponse,
)
from app.services.ollama_service import OllamaService
from app.services.gemini_service import GeminiService

ollama = OllamaService()
gemini = GeminiService()

SHIPPING_LABEL = {
    "FREE": "무료배송",
    "STANDARD": "일반배송",
    "EXPRESS": "로켓배송",
    "NEXT_DAY": "익일배송",
}


def build_prompt(request: ShoppingExplainRequest) -> str:
    ingredient = request.ingredientName

    # 쇼핑 컨텍스트
    if request.shoppingItems:
        best = request.shoppingItems[0]
        price_str = f"{best.price:,}원"
        shipping_str = SHIPPING_LABEL.get(best.shippingType, best.shippingType)
        mall_str = best.mallName
        discount_str = f", {best.discountRate}% 할인" if best.discountRate else ""
        shopping_context = f"최저가 상품: {mall_str}에서 {price_str} {shipping_str}{discount_str}"
    elif request.lowestPrice:
        shopping_context = f"최저가: {request.lowestPrice:,}원"
    else:
        shopping_context = "가격 정보 없음"

    # 레시피 컨텍스트
    if request.recipeTitle:
        matched = ", ".join(request.matchedIngredients) if request.matchedIngredients else "없음"
        recipe_context = f"""
레시피 정보:
- 레시피명: {request.recipeTitle}
- 이 레시피에 필요한 재료: {ingredient}
- 이미 보유한 재료: {matched}
""".strip()
    else:
        recipe_context = None

    if recipe_context:
        prompt = f"""
너는 쇼핑 추천 이유를 설명하는 AI다.

역할:
- 사용자가 레시피를 만들기 위해 재료를 구매하려 한다.
- 왜 이 재료가 필요한지, 왜 이 상품이 좋은지 자연스럽게 1문장으로 설명한다.

중요 제약:
- 입력에 없는 정보를 절대 만들어내지 않는다.
- 의학적 효능, 건강 효과를 말하지 않는다.
- 과장하지 않는다.
- 레시피명과 재료명을 함께 자연스럽게 언급한다.

작성 규칙:
- 한국어 1문장으로 작성한다.
- 불릿, 제목, 따옴표 없이 사용자에게 보여줄 문장만 출력한다.

사용 가능한 정보:
{recipe_context}
{shopping_context}

추천 이유:
""".strip()
    else:
        prompt = f"""
너는 쇼핑 추천 이유를 설명하는 AI다.

역할:
- 사용자가 재료를 구매하려 한다.
- 가격, 배송, 할인 정보를 바탕으로 왜 이 상품이 좋은지 1문장으로 설명한다.

중요 제약:
- 입력에 없는 정보를 절대 만들어내지 않는다.
- 의학적 효능, 건강 효과를 말하지 않는다.
- 과장하지 않는다.

작성 규칙:
- 한국어 1문장으로 작성한다.
- 불릿, 제목, 따옴표 없이 사용자에게 보여줄 문장만 출력한다.

사용 가능한 정보:
재료명: {ingredient}
{shopping_context}

추천 이유:
""".strip()

    return prompt


def generate_shopping_explanation(request: ShoppingExplainRequest) -> ShoppingExplainResponse:
    prompt = build_prompt(request)

    try:
        explanation = ollama.generate(prompt)
    except Exception:
        explanation = gemini.generate(prompt)

    return ShoppingExplainResponse(explanation=explanation)
