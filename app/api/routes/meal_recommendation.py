# 이 파일은 Java 백엔드(Meal Controller)에서 호출하는 식단 추천 API의 엔드포인트를 정의합니다.

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import os

from app.db import get_db
from app.services.meal_recommendation_service import MealRecommendationService

# API 라우터를 생성합니다. 접두사로 /meal-recommendation을 사용합니다.
router = APIRouter(prefix="/meal-recommendation", tags=["Meal Recommendation"])





# 내부 서비스 호출을 검증하는 함수입니다.
def verify_internal_call(
    x_internal_service: str = Header(default=None, alias="X-Internal-Service"),
    x_internal_token: str = Header(default=None, alias="X-Internal-Token"),
):
    """
    Spring Boot 서버에서 전송한 인증 헤더를 확인하여 외부에서의 무단 접근을 차단합니다.
    """
    expected_token = os.getenv("INTERNAL_API_TOKEN")

    if x_internal_service not in ["spring-boot", "spring-backend"]:
        raise HTTPException(status_code=403, detail="유효하지 않은 X-Internal-Service 헤더입니다.")

    if x_internal_token != expected_token:
        raise HTTPException(status_code=403, detail="유효하지 않은 X-Internal-Token 헤더입니다.")


# API 요청 형식을 정의합니다.
class MealRecommendationRequest(BaseModel):
    user_id: str
    height: float
    weight: float
    age: int
    gender: str


class RecipeBrief(BaseModel):
    recipe_id: int
    title: str
    thumbnail_url: Optional[str] = None


# Fix #2 & #4: 응답 형식을 명시적으로 정의합니다.
# recommendations 값은 List[RecipeBrief] 로 강제하여 Spring Boot 와 일치시킵니다.
class MealRecommendationResponse(BaseModel):
    report: str
    recommendations: Dict[str, List[RecipeBrief]]


# Spring Boot FastApiMealEnvelope.java 와 필드 완전 일치
class FastApiMealEnvelope(BaseModel):
    success: bool
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[MealRecommendationResponse] = None  # Fix #2: Pydantic 직렬화 보장
    requestId: Optional[str] = None


# 식단 추천을 처리하는 POST 엔드포인트입니다.
@router.post("", response_model=FastApiMealEnvelope)
def get_meal_recommendation(
    request: MealRecommendationRequest,
    db=Depends(get_db),
    _=Depends(verify_internal_call),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
):
    """
    Java Meal Controller로부터 호출되어 사용자의 30일 영양 기록을 분석하고 레시피를 추천합니다.
    """
    try:
        service = MealRecommendationService(db)
        # Fix #2: 서비스가 반환한 dict 를 Pydantic 모델로 변환하여 직렬화 보장
        raw = service.analyze_and_recommend(request)
        result = MealRecommendationResponse(
            report=raw["report"],
            recommendations=raw["recommendations"],
        )
        return FastApiMealEnvelope(
            success=True,
            code="OK",
            message="식단 추천이 성공적으로 완료되었습니다.",
            data=result,
            requestId=x_request_id,
        )
    except HTTPException:
        raise  # verify_internal_call 에서 발생한 HTTPException 은 그대로 전달
    except Exception as e:
        # Fix #5: 예외도 봉투 형식으로 반환하여 Spring Boot 파싱 실패 방지
        raise HTTPException(status_code=500, detail={
            "success": False,
            "code": "INTERNAL_ERROR",
            "message": str(e),
            "data": None,
            "requestId": x_request_id,
        })
