from fastapi import APIRouter

from app.schemas.substitution_llm import (
    SubstitutionLlmRequest,
    SubstitutionLlmResponse,
)
from app.services.substitution_service import suggest_substitutions

router = APIRouter(
    prefix="/internal/llm/substitutions",
    tags=["substitution-llm"],
)


@router.post("/suggest", response_model=SubstitutionLlmResponse)
def suggest(request: SubstitutionLlmRequest):
    return suggest_substitutions(request)