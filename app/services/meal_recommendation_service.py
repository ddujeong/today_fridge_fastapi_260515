# 이 파일은 사용자의 식습관을 분석하고 Gemini AI를 사용하여 맞춤형 레시피를 추천하는 서비스 클래스입니다.

from google import genai
from app.models.nutrition_db import DailyNutritionHistory, RecipeNutrition
from app.Prompt.MealAnalysis import get_meal_analysis_prompt
import os
import json
from datetime import date, timedelta

class MealRecommendationService:
    """
    사용자의 영양 섭취 기록을 바탕으로 분석 보고서를 작성하고 식단을 추천합니다.
    """
    def __init__(self, db):
        # 데이터베이스 커서를 저장합니다.
        self.db = db
        # 환경 변수에서 Gemini API 키를 가져와 설정합니다.
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
        # 요청받은 Gemma 모델을 설정합니다.
        self.model_name = "gemma-4-26b-a4b"

    def analyze_and_recommend(self, request):
        """
        사용자의 최근 30일간의 데이터를 분석하여 아침, 점심, 저녁 레시피를 추천합니다.
        요청에 포함된 신체 정보(키, 몸무게, 나이, 성별)를 분석에 반영합니다.
        """
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

        # 1 & 2단계: 지난 30일 및 7일간의 영양 섭취 기록을 가져옵니다.
        # Raw SQL을 사용하여 데이터를 조회합니다.
        self.db.execute("""
            SELECT * FROM day_nutrition 
            WHERE user_id = %s AND date >= %s
        """, (uid, thirty_days_ago_dt))
        rows = self.db.fetchall()
        month_history = [DailyNutritionHistory(**row) for row in rows]

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

        # Fix #2: 7일 필터도 datetime 기준으로 통일합니다.
        week_history = [
            h for h in month_history
            if getattr(h, "date") is not None and (
                h.date >= seven_days_ago_dt
                if isinstance(h.date, dt)
                else h.date >= seven_days_ago
            )
        ]
        week_cal = get_avg(week_history, "total_calories")
        week_carbs = get_avg(week_history, "total_carbs")
        week_protein = get_avg(week_history, "total_protein")
        week_fat = get_avg(week_history, "total_fat")
        week_sugar = get_avg(week_history, "total_sugar")
        week_sodium = get_avg(week_history, "total_sodium")
        week_chol = get_avg(week_history, "total_cholesterol")

        # 3 & 4단계: Gemini API를 사용하여 식습관을 분석합니다.
        # 밥 한 공기를 함께 먹는다는 전제 조건과 사용자의 신체 정보를 포함합니다.
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
            # AI 모델로부터 응답을 생성하고 JSON을 파싱합니다.
            response = self.client.models.generate_content(model=self.model_name, contents=prompt)
            response_text = response.text.strip()
            
            # 마크다운 블록 제거
            if response_text.startswith("```json"):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith("```"):
                response_text = response_text[3:-3].strip()
            
            ai_analysis = json.loads(response_text)
        except Exception as e:
            # 오류 발생 시 기본 목표값을 설정합니다.
            ai_analysis = {
                "analysis_report": f"분석 중 오류가 발생했습니다: {str(e)}",
                "targets": {
                    "breakfast": {"calories": 500, "carbs": 60, "protein": 20, "fat": 15, "sugar": 10, "sodium": 400, "cholesterol": 30},
                    "lunch": {"calories": 600, "carbs": 70, "protein": 30, "fat": 20, "sugar": 10, "sodium": 500, "cholesterol": 40},
                    "dinner": {"calories": 500, "carbs": 60, "protein": 30, "fat": 15, "sugar": 10, "sodium": 400, "cholesterol": 30}
                }
            }

        # 5단계: 분석된 목표에 가장 적합한 레시피를 DB에서 찾습니다.
        # recipes 테이블과 JOIN하여 제목과 썸네일 정보를 함께 가져옵니다.
        self.db.execute("""
            SELECT rn.*, r.title, r.thumbnail_url 
            FROM recipe_nutrition rn
            JOIN recipes r ON rn.recipe_id = r.recipe_id
        """)
        rows = self.db.fetchall()
        recipes = [RecipeNutrition(**row) for row in rows]
        # Fix #3: 레시피가 없는 경우 명확한 오류 메시지를 반환합니다.
        if not recipes:
            raise ValueError("추천할 레시피 데이터가 존재하지 않습니다. recipe_nutrition 및 recipes 테이블을 확인해주세요.")
        
        # 밥 한 공기의 영양 정보입니다.
        rice_nutrition = {
            "calories": 200, "carbs": 45, "protein": 4, "fat": 0.4, 
            "sugar": 0, "sodium": 0, "cholesterol": 0
        }
        
        recommended_recipes = {"breakfast": [], "lunch": [], "dinner": []}

        for meal_type in ["breakfast", "lunch", "dinner"]:
            target = ai_analysis["targets"].get(meal_type, {})
            
            # 밥을 제외하고 레시피 자체가 제공해야 할 목표 영양소를 계산합니다.
            ideal_recipe_cal = max(0, target.get("calories", 500) - rice_nutrition["calories"])
            ideal_recipe_carbs = max(0, target.get("carbs", 60) - rice_nutrition["carbs"])
            ideal_recipe_protein = max(0, target.get("protein", 20) - rice_nutrition["protein"])
            ideal_recipe_fat = max(0, target.get("fat", 15) - rice_nutrition["fat"])
            ideal_recipe_sugar = max(0, target.get("sugar", 10) - rice_nutrition["sugar"])
            ideal_recipe_sodium = max(0, target.get("sodium", 400) - rice_nutrition["sodium"])
            ideal_recipe_chol = max(0, target.get("cholesterol", 30) - rice_nutrition["cholesterol"])

            # 레시피와 목표값 사이의 차이를 점수로 환산하는 함수입니다. (낮을수록 좋음)
            def recipe_score(r):
                r_cal = r.calories or 0
                r_carbs = r.carbs or 0
                r_protein = r.protein or 0
                r_fat = r.fat or 0
                r_sugar = r.sugar or 0
                r_sodium = r.sodium or 0
                r_chol = r.cholesterol or 0
                
                # 주요 영양소 점수 계산 (칼로리 당 에너지 계수 적용)
                macro_score = (
                    abs(r_cal - ideal_recipe_cal) + 
                    abs(r_carbs - ideal_recipe_carbs) * 4 + 
                    abs(r_protein - ideal_recipe_protein) * 4 + 
                    abs(r_fat - ideal_recipe_fat) * 9
                )
                
                # 미량 영양소 점수 계산
                micro_score = (
                    abs(r_sugar - ideal_recipe_sugar) * 4 + 
                    abs(r_sodium - ideal_recipe_sodium) * 0.1 + 
                    abs(r_chol - ideal_recipe_chol) * 0.1
                )
                
                return macro_score + micro_score

            # 목표에 가장 가까운 상위 3개의 레시피를 선택합니다.
            recipes_sorted = sorted(recipes, key=recipe_score)
            top_3 = recipes_sorted[:3]
            
            # 레시피 ID 대신 상세 정보를 포함한 딕셔너리 리스트를 저장합니다.
            recommended_recipes[meal_type] = [
                {
                    "recipe_id": r.recipe_id,
                    "title": r.title,
                    "thumbnail_url": r.thumbnail_url
                } for r in top_3
            ]

        # 6단계: 분석 보고서와 추천 레시피 상세 정보를 반환합니다.
        return {
            "report": ai_analysis["analysis_report"],
            "recommendations": recommended_recipes
        }
