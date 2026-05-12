from pydantic import BaseModel
from typing import List, Dict, Any

class HealthReportRequest(BaseModel):
    fridge_ingredients: List[str]
    recent_meals: List[Dict[str, Any]]

class HealthReportResponse(BaseModel):
    summary: str
    advice: List[str]
    meals: List[str]
    videos: List[str]
