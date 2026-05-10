# 이 파일은 데이터베이스의 영양 정보를 표현하는 클래스들을 정의합니다.
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class DailyNutritionHistory:
    """
    사용자의 하루 영양소 섭취 내역을 표현합니다.
    """
    day_nutrition_id: int
    user_id: int
    date: datetime
    total_calories: float = 0.0
    total_carbs: float = 0.0
    total_protein: float = 0.0
    total_fat: float = 0.0
    total_sugar: float = 0.0
    total_sodium: float = 0.0
    total_cholesterol: float = 0.0

@dataclass
class RecipeNutrition:
    """
    레시피의 영양 정보를 표현합니다.
    """
    recipe_nutrition_id: int
    recipe_id: int
    calories: Optional[float] = 0.0
    carbs: Optional[float] = 0.0
    protein: Optional[float] = 0.0
    fat: Optional[float] = 0.0
    sugar: Optional[float] = 0.0
    sodium: Optional[float] = 0.0
    cholesterol: Optional[float] = 0.0
    title: Optional[str] = ""
    thumbnail_url: Optional[str] = None
