from fastapi import APIRouter, Depends
from app.schemas.health_report_schema import HealthReportRequest, HealthReportResponse
from app.services.gemini_service import GeminiService
import json

import logging

router = APIRouter()
gemini_service = GeminiService()
logger = logging.getLogger(__name__)

@router.post("/health-report/generate", response_model=HealthReportResponse)
async def generate_health_report(request: HealthReportRequest):
    prompt = f"""
You are an expert AI nutritionist. Analyze the user's eating habits and recommend meals based strictly on their current fridge inventory.

Context:
- Current Fridge Ingredients: {', '.join(request.fridge_ingredients)}
- Recent Meal Logs: {json.dumps(request.recent_meals, ensure_ascii=False)}

Constraint:
Recommended recipes MUST strictly use ingredients found in the provided fridge data.
ALL RESPONSES MUST BE IN KOREAN (한국어).

Output must be in JSON format matching the following structure:
{{
    "summary": "General statement on current eating habits in Korean.",
    "advice": ["What to eat more of in Korean", "What to eat less of in Korean"],
    "meals": ["Breakfast recipe using fridge ingredients", "Lunch recipe", "Dinner recipe"],
    "videos": ["YouTube search term for breakfast in Korean", "YouTube search term for lunch in Korean", "YouTube search term for dinner in Korean"]
}}
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
