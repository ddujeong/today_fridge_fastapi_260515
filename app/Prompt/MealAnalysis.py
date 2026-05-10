def get_meal_analysis_prompt(
    gender_kr: str,
    age: int,
    height: float,
    weight: float,
    month_cal: float,
    month_carbs: float,
    month_protein: float,
    month_fat: float,
    month_sugar: float,
    month_sodium: float,
    month_chol: float,
    week_cal: float,
    week_carbs: float,
    week_protein: float,
    week_fat: float,
    week_sugar: float,
    week_sodium: float,
    week_chol: float
) -> str:
    """
    Generates the prompt for the Gemini AI model to analyze meal history and recommend targets.
    """
    return f"""
        사용자 신체 정보:
        - 성별: {gender_kr}
        - 나이: {age}세
        - 키: {height:.1f}cm
        - 몸무게: {weight:.1f}kg

        사용자 식습관 분석 데이터:
        최근 30일 평균 - 칼로리: {month_cal:.1f}, 탄수화물: {month_carbs:.1f}g, 단백질: {month_protein:.1f}g, 지방: {month_fat:.1f}g, 당류: {month_sugar:.1f}g, 나트륨: {month_sodium:.1f}mg, 콜레스테롤: {month_chol:.1f}mg.
        최근 7일 평균 - 칼로리: {week_cal:.1f}, 탄수화물: {week_carbs:.1f}g, 단백질: {week_protein:.1f}g, 지방: {week_fat:.1f}g, 당류: {week_sugar:.1f}g, 나트륨: {week_sodium:.1f}mg, 콜레스테롤: {week_chol:.1f}mg.

        위 신체 정보와 식습관을 종합적으로 분석해주세요. 부족한 영양소와 줄여야 할 영양소는 무엇인가요?
        다음 식사(아침, 점심, 저녁)에 대한 이상적인 영양소 목표를 제안해주세요.
        모든 식사는 밥 한 공기(약 200kcal, 탄수화물 45g, 단백질 4g, 지방 0.4g, 당류 0g, 나트륨 0mg, 콜레스테롤 0mg)를 함께 먹는다고 가정합니다.
        결과는 반드시 아래 구조의 JSON 형식으로만 응답해주세요:
        {{
            "analysis_report": "상세 분석 내용...",
            "targets": {{
                "breakfast": {{"calories": 0, "carbs": 0, "protein": 0, "fat": 0, "sugar": 0, "sodium": 0, "cholesterol": 0}},
                "lunch": {{"calories": 0, "carbs": 0, "protein": 0, "fat": 0, "sugar": 0, "sodium": 0, "cholesterol": 0}},
                "dinner": {{"calories": 0, "carbs": 0, "protein": 0, "fat": 0, "sugar": 0, "sodium": 0, "cholesterol": 0}}
            }}
        }}
        """
