# 이 파일은 사용자의 식습관을 분석하고 Gemini AI를 사용하여 맞춤형 레시피를 추천하는 서비스 클래스입니다.

from app.models.nutrition_db import DailyNutritionHistory, RecipeNutrition
from app.Prompt.MealAnalysis import get_meal_analysis_prompt
from app.services.gemini_service import GeminiService
import os
import json
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

class MealRecommendationService:
    """
    사용자의 영양 섭취 기록을 바탕으로 분석 보고서를 작성하고 식단을 추천합니다.
    """
    def __init__(self, db):
        # 데이터베이스 커서를 저장합니다.
        self.db = db
        # GeminiService를 사용합니다.
        self.gemini_service = GeminiService()

    def analyze_and_recommend(self, request):
        """
        사용자의 최근 30일간의 데이터를 분석하여 아침, 점심, 저녁 레시피를 추천합니다.
        요청에 포함된 신체 정보(키, 몸무게, 나이, 성별)를 분석에 반영합니다.
        """
        try:
            # 분석을 위한 기준 날짜들을 설정합니다.
            from datetime import datetime as dt
            today = date.today()
            thirty_days_ago = today - timedelta(days=30)
            seven_days_ago = today - timedelta(days=7)
            
            # Fix #2: DB DateTime 컬럼과 비교할 때 datetime 으로 변환합니다.
            thirty_days_ago_dt = dt.combine(thirty_days_ago, dt.min.time())
            seven_days_ago_dt = dt.combine(seven_days_ago, dt.min.time())

            # user_id를 숫자로 변환합니다.
            try:
                uid = int(request.user_id)
            except ValueError:
                uid = request.user_id

            logger.info(f"Fetching nutrition history for user {uid}")

            # 1 & 2단계: 지난 30일 및 7일간의 영양 섭취 기록을 가져옵니다.
            # Raw SQL을 사용하여 데이터를 조회합니다.
            self.db.execute("""
                SELECT * FROM day_nutrition 
                WHERE user_id = %s AND date >= %s
            """, (uid, thirty_days_ago_dt))
            rows = self.db.fetchall()
            
            # Dataclass 필드만 추출하여 안전하게 생성합니다.
            from dataclasses import fields
            history_fields = {f.name for f in fields(DailyNutritionHistory)}
            month_history = [
                DailyNutritionHistory(**{k: v for k, v in row.items() if k in history_fields})
                for row in rows
            ]

            # 평균 영양소 섭취량을 계산하는 내부 함수입니다.
            def get_avg(history, attr):
                if not history: return 0.0
                total = sum(getattr(h, attr) for h in history if getattr(h, attr) is not None)
                return total / len(history)

            # 30일 평균 계산
            month_cal = get_avg(month_history, "total_calories")
            month_carbs = get_avg(month_history, "total_carbs")
            month_protein = get_avg(month_history, "total_protein")
            month_fat = get_avg(month_history, "total_fat")
            month_sugar = get_avg(month_history, "total_sugar")
            month_sodium = get_avg(month_history, "total_sodium")
            month_chol = get_avg(month_history, "total_cholesterol")

            # 7일 평균 계산
            week_history = []
            for h in month_history:
                if getattr(h, "date") is None:
                    continue
                # Make timezone-aware DB datetimes naive for comparison
                h_date = h.date.replace(tzinfo=None) if isinstance(h.date, dt) else h.date
                if h_date >= seven_days_ago_dt if isinstance(h_date, dt) else h_date >= seven_days_ago:
                    week_history.append(h)
            week_cal = get_avg(week_history, "total_calories")
            week_carbs = get_avg(week_history, "total_carbs")
            week_protein = get_avg(week_history, "total_protein")
            week_fat = get_avg(week_history, "total_fat")
            week_sugar = get_avg(week_history, "total_sugar")
            week_sodium = get_avg(week_history, "total_sodium")
            week_chol = get_avg(week_history, "total_cholesterol")

            # 3 & 4단계: Gemini API를 사용하여 식습관을 분석합니다.
            gender_kr = "남성" if request.gender.upper() == "MALE" else "여성"
            
            prompt = get_meal_analysis_prompt(
                gender_kr=gender_kr,
                age=request.age,
                height=request.height,
                weight=request.weight,
                month_cal=month_cal,
                month_carbs=month_carbs,
                month_protein=month_protein,
                month_fat=month_fat,
                month_sugar=month_sugar,
                month_sodium=month_sodium,
                month_chol=month_chol,
                week_cal=week_cal,
                week_carbs=week_carbs,
                week_protein=week_protein,
                week_fat=week_fat,
                week_sugar=week_sugar,
                week_sodium=week_sodium,
                week_chol=week_chol
            )

            try:
                # GeminiService를 통해 응답 생성
                response_text = self.gemini_service.generate(prompt)
                
                # 마크다운 블록 제거
                if response_text.startswith("```json"):
                    response_text = response_text[7:-3].strip()
                elif response_text.startswith("```"):
                    response_text = response_text[3:-3].strip()
                
                ai_analysis = json.loads(response_text)
            except Exception as e:
                logger.error(f"AI analysis or parsing failed: {str(e)}")
                # 오류 발생 시 기본 목표값을 설정합니다.
                ai_analysis = {
                    "analysis_report": f"분석 중 오류가 발생했습니다: {str(e)}",
                    "targets": {
                        "breakfast": {"calories": 500, "carbs": 60, "protein": 20, "fat": 15, "sugar": 10, "sodium": 400, "cholesterol": 30},
                        "lunch": {"calories": 600, "carbs": 70, "protein": 30, "fat": 20, "sugar": 10, "sodium": 500, "cholesterol": 40},
                        "dinner": {"calories": 500, "carbs": 60, "protein": 30, "fat": 15, "sugar": 10, "sodium": 400, "cholesterol": 30}
                    }
                }

            # 5단계: 레시피 추천 로직
            self.db.execute("""
                SELECT rn.*, r.title, r.thumbnail_url 
                FROM recipe_nutrition rn
                JOIN recipes r ON rn.recipe_id = r.recipe_id
            """)
            rows = self.db.fetchall()
            
            recipe_fields = {f.name for f in fields(RecipeNutrition)}
            recipes = [
                RecipeNutrition(**{k: v for k, v in row.items() if k in recipe_fields})
                for row in rows
            ]
            
            if not recipes:
                logger.error("No recipes found in database")
                raise ValueError("추천할 레시피 데이터가 존재하지 않습니다. recipe_nutrition 및 recipes 테이블을 확인해주세요.")
            
            rice_nutrition = {
                "calories": 200, "carbs": 45, "protein": 4, "fat": 0.4, 
                "sugar": 0, "sodium": 0, "cholesterol": 0
            }
            
            recommended_recipes = {"breakfast": [], "lunch": [], "dinner": []}

            for meal_type in ["breakfast", "lunch", "dinner"]:
                target = ai_analysis["targets"].get(meal_type, {})
                
                ideal_recipe_cal = max(0, target.get("calories", 500) - rice_nutrition["calories"])
                ideal_recipe_carbs = max(0, target.get("carbs", 60) - rice_nutrition["carbs"])
                ideal_recipe_protein = max(0, target.get("protein", 20) - rice_nutrition["protein"])
                ideal_recipe_fat = max(0, target.get("fat", 15) - rice_nutrition["fat"])
                ideal_recipe_sugar = max(0, target.get("sugar", 10) - rice_nutrition["sugar"])
                ideal_recipe_sodium = max(0, target.get("sodium", 400) - rice_nutrition["sodium"])
                ideal_recipe_chol = max(0, target.get("cholesterol", 30) - rice_nutrition["cholesterol"])

                def recipe_score(r):
                    r_cal = float(r.calories or 0)
                    r_carbs = float(r.carbs or 0)
                    r_protein = float(r.protein or 0)
                    r_fat = float(r.fat or 0)
                    r_sugar = float(r.sugar or 0)
                    r_sodium = float(r.sodium or 0)
                    r_chol = float(r.cholesterol or 0)
                    
                    macro_score = (
                        abs(r_cal - ideal_recipe_cal) + 
                        abs(r_carbs - ideal_recipe_carbs) * 4 + 
                        abs(r_protein - ideal_recipe_protein) * 4 + 
                        abs(r_fat - ideal_recipe_fat) * 9
                    )
                    
                    micro_score = (
                        abs(r_sugar - ideal_recipe_sugar) * 4 + 
                        abs(r_sodium - ideal_recipe_sodium) * 0.1 + 
                        abs(r_chol - ideal_recipe_chol) * 0.1
                    )
                    
                    return macro_score + micro_score

                recipes_sorted = sorted(recipes, key=recipe_score)
                top_3 = recipes_sorted[:3]
                
                recommended_recipes[meal_type] = [
                    {
                        "recipe_id": r.recipe_id,
                        "title": r.title,
                        "thumbnail_url": r.thumbnail_url
                    } for r in top_3
                ]

            return {
                "report": ai_analysis["analysis_report"],
                "recommendations": recommended_recipes
            }
        except Exception as e:
            logger.exception(f"Fatal error in analyze_and_recommend: {str(e)}")
            raise
