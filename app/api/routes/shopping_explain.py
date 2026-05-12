from fastapi import APIRouter

from app.schemas.shopping_explain_schema import (
    ShoppingExplainRequest,
    ShoppingExplainResponse,
)
from app.services.shopping_explanation_service import generate_shopping_explanation

router = APIRouter(
    prefix="/internal/llm",
    tags=["shopping-llm"],
)


@router.post(
    "/shopping/explain",
    response_model=ShoppingExplainResponse,
)
def explain_shopping(request: ShoppingExplainRequest):
    return generate_shopping_explanation(request)
