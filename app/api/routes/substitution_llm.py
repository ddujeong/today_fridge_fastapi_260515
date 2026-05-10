from fastapi import APIRouter

from app.schemas.substitution_llm import (
    SubstitutionLlmRequest,
    SubstitutionLlmResponse,
    SubstitutionLlmResult,
)

router = APIRouter(
    prefix="/internal/llm/substitutions",
    tags=["substitution-llm"],
)


@router.post("/suggest", response_model=SubstitutionLlmResponse)
def suggest_substitutions(request: SubstitutionLlmRequest):
    results = []

    for missing in request.missingIngredients:
        results.append(
            SubstitutionLlmResult(
                missingIngredient=missing,
                decisionType="REQUIRED",
                substituteIngredient=None,
                reason="현재는 FastAPI 연동 검증용 기본 응답입니다.",
            )
        )

    return SubstitutionLlmResponse(results=results)