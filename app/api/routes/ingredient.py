from fastapi import APIRouter
from app.models.expiration import EstimateExpirationRequest, EstimateExpirationResponse
from app.services.expiration_service import estimate_expiration

router = APIRouter()


@router.post("/ingredient/estimate-expiration", response_model=EstimateExpirationResponse)
def estimate_expiration_date(req: EstimateExpirationRequest) -> EstimateExpirationResponse:
    """
    카테고리 + 보관방식 기반 유통기한 추정 (규칙 기반).
    유통기한 미입력 식재료에 대해 Spring Boot 백엔드가 호출.
    """
    result = estimate_expiration(req.category_code, req.storage_type)
    return EstimateExpirationResponse(**result)
