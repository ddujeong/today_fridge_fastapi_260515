from fastapi import APIRouter

from app.schemas.recommendation_explanation_schema import (
    RecommendationExplainRequest,
    RecommendationExplainResponse,
)
from app.services.recommendation_explanation_service import (
    generate_recommendation_explanation,
)
router = APIRouter(
    prefix="/internal/llm",
    tags=["recommendation-llm"]
)


@router.post(
    "/recommendation/explain",
    response_model=RecommendationExplainResponse,
)
def explain_recommendation(
    request: RecommendationExplainRequest,
):
    return generate_recommendation_explanation(request)