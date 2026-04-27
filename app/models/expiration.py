from pydantic import BaseModel
from typing import Optional


class EstimateExpirationRequest(BaseModel):
    name: Optional[str] = None
    category_code: Optional[str] = None
    storage_type: Optional[str] = None


class EstimateExpirationResponse(BaseModel):
    estimated_expiration_date: str   # ISO 날짜 문자열 (yyyy-MM-dd)
    base_days: int
    estimated_by: str                # rule:category+storage | rule:storage_only | rule:default
    needs_review: bool
