from app.schemas.recommendation_explanation_schema import RecommendationExplainRequest, RecommendationExplainResponse


def generate_recommendation_explanation(
    request: RecommendationExplainRequest,
) -> RecommendationExplainResponse:
    return RecommendationExplainResponse(
        explanation=f"{request.title}은(는) 보유 재료와 사용자 조건을 고려해 추천되었습니다."
    )