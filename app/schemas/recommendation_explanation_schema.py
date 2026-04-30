from typing import List, Optional
from pydantic import BaseModel


class RecommendationExplainRequest(BaseModel):
    recipeId: int
    title: str
    matchedIngredients: List[str] = []
    missingIngredients: List[str] = []
    conditionTags: List[str] = []
    matchRate: float
    totalScore: float
    semanticScore: float
    hybridScore: float
    reason: Optional[str] = None


class RecommendationExplainResponse(BaseModel):
    explanation: str