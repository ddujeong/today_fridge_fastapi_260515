from fastapi import APIRouter, Depends
from app.schemas.health_report_schema import HealthReportRequest, HealthReportResponse
from app.services.gemini_service import GeminiService
from app.db import get_db
import json

import logging

router = APIRouter()
gemini_service = GeminiService()
logger = logging.getLogger(__name__)

@router.post("/health-report/generate", response_model=HealthReportResponse)
async def generate_health_report(request: HealthReportRequest, db=Depends(get_db)):
    # Fetch some recipes from the DB to provide as context
    try:
        db.execute("SELECT title FROM recipes LIMIT 50")
        db_recipes = db.fetchall()
        recipe_titles = [r['title'] for r in db_recipes]
    except Exception as e:
        logger.error(f"Failed to fetch recipes from DB: {str(e)}")
        recipe_titles = []

    prompt = f"""
당신은 대한민국 최고의 AI 영양사이자 건강 분석 전문가입니다. 
사용자의 식습관 기록과 현재 냉장고에 있는 재료를 분석하여, 과학적이고 구체적인 건강 레포트를 작성해주세요.

[분석 데이터]
1. 현재 냉장고 재료: {', '.join(request.fridge_ingredients) if request.fridge_ingredients else '없음'}
2. 최근 식사 기록: {json.dumps(request.recent_meals, ensure_ascii=False)}

[추천 가능한 레시피 목록 (DB 내 실제 레시피)]
{', '.join(recipe_titles) if recipe_titles else '현재 DB에 레시피가 부족합니다. 일반적인 건강식을 추천해주세요.'}

[작성 가이드라인]
- **총평 (Summary)**: 단순히 나열하는 것이 아니라, 사용자의 영양 균형(탄수화물, 단백질, 지방, 나트륨 등)을 심층적으로 분석하세요. 현재 식습관의 장점과 반드시 개선해야 할 점을 전문가의 시선으로 설명하세요.
- **영양 어드바이스 (Advice)**: 구체적인 수치나 영양소 명칭을 언급하며, 무엇을 더 먹고 무엇을 피해야 하는지 3가지 이상 제시하세요.
- **식단 추천 (Meals)**: 반드시 위 '추천 가능한 레시피 목록'에 있는 레시피 중에서 사용자의 냉장고 재료와 영양 상태에 가장 적합한 것을 골라 아침, 점심, 저녁 순으로 추천하세요. 만약 목록에 적절한 것이 없다면 가장 유사한 요리를 제안하세요.
- **영상 검색 (Videos)**: 추천한 식단의 레시피를 배울 수 있는 최적의 유튜브 검색어를 한국어로 생성하세요.

[출력 형식]
반드시 아래 구조의 JSON 형식으로만 응답하세요:
{{
    "summary": "전문적이고 상세한 식단 분석 및 건강 조언 (Markdown 형식 활용 가능)",
    "advice": ["구체적인 영양 조언 1", "구체적인 영양 조언 2", "구체적인 영양 조언 3"],
    "meals": ["추천 아침 레시피 명칭", "추천 점심 레시피 명칭", "추천 저녁 레시피 명칭"],
    "videos": ["아침 레시피 유튜브 검색어", "점심 레시피 유튜브 검색어", "저녁 레시피 유튜브 검색어"]
}}

모든 응답은 반드시 한국어(Korean)로 작성하세요.
"""
    try:
        response_text = gemini_service.generate_health_report(prompt)
        # Handle markdown blocks if present
        if response_text.startswith("```json"):
            response_text = response_text[7:-3].strip()
        elif response_text.startswith("```"):
            response_text = response_text[3:-3].strip()
            
        data = json.loads(response_text)
        return HealthReportResponse(**data)
    except Exception as e:
        logger.error(f"Health Report Generation Failed: {str(e)}")
        # Fallback or error handling
        return HealthReportResponse(
            summary=f"AI 분석 중 오류가 발생했습니다: {str(e)}",
            advice=[],
            meals=[],
            videos=[]
        )
