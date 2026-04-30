from pydantic import BaseModel
from typing import Optional


class ClassifyCategoryRequest(BaseModel):
    name: str


class ClassifyCategoryResponse(BaseModel):
    category_code: str
    category_name: str
    matched_keyword: Optional[str] = None
    confidence: float
