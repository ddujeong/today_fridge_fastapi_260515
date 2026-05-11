from typing import List, Optional
from pydantic import BaseModel


class SubstitutionLlmRequest(BaseModel):
    recipeTitle: str
    recipeIngredients: List[str]
    ownedIngredients: List[str]
    missingIngredients: List[str]


class SubstitutionLlmResult(BaseModel):
    missingIngredient: str
    decisionType: str
    substituteIngredient: Optional[str] = None
    reason: str


class SubstitutionLlmResponse(BaseModel):
    results: List[SubstitutionLlmResult]