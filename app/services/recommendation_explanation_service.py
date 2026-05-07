from app.schemas.recommendation_explanation_schema import (
    RecommendationExplainRequest,
    RecommendationExplainResponse,
)

from app.services.ollama_service import OllamaService
from app.services.gemini_service import GeminiService

ollama = OllamaService()
gemini = GeminiService()


def build_prompt(request: RecommendationExplainRequest) -> str:
    matched = ", ".join(request.matchedIngredients) if request.matchedIngredients else "없음"
    missing = ", ".join(request.missingIngredients) if request.missingIngredients else "없음"
    conditions = ", ".join(request.conditionTags) if request.conditionTags else "없음"

    return f"""
너는 레시피 추천 결과를 설명하는 AI다.

역할:
- 추천 판단은 이미 백엔드 시스템이 완료했다.
- 너는 판단을 바꾸지 않고, 추천 이유만 자연스럽게 설명한다.

중요 제약:
- 레시피명을 문장 안에서 반복하지 않는다.
- 입력에 없는 재료를 절대 언급하지 않는다.
- matchedIngredients에 있는 재료만 보유 재료라고 말한다.
- missingIngredients에 없는 재료를 부족하다고 말하지 않는다.
- 부족 재료가 있어도 완성 가능하다고 단정하지 않는다.
- conditionTags는 사용자 조건일 뿐, 레시피에 해당 재료가 들어간다는 뜻이 아니다.
- 알러지 조건은 "조건을 고려했다" 정도로만 표현한다.
- 의학적 판단, 건강 효과, 치료 효과를 말하지 않는다.
- 점수 계산 방식을 새로 해석하지 않는다.
- 과장하지 않는다.

작성 규칙:
- 한국어로 작성한다.
- 1문장으로 짧게 작성한다.
- 사용자에게 보여줄 문장만 출력한다.
- 불릿, 제목, 따옴표 없이 작성한다.
- "추가 확인이 필요합니다"라는 표현은 쓰지 않는다.
- "이 레시피는", "다음 레시피는" 같은 반복 표현을 피한다.

사용 가능한 정보:
레시피명: {request.title}
매칭 재료: {matched}
부족 재료: {missing}
사용자 조건: {conditions}
기본 추천 이유: {request.reason}

추천 설명:
""".strip()


def generate_recommendation_explanation(request):

    prompt = build_prompt(request)

    try:
        explanation = ollama.generate(prompt)

    except Exception:
        explanation = gemini.generate(prompt)

    return RecommendationExplainResponse(
        explanation=explanation
    )