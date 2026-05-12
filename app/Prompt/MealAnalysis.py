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
    week_chol: float,
    available_recipes: str
) -> str:
    """
    Generates the prompt for the Gemini AI model to analyze meal history, 
    recommend targets, and suggest specific recipes from the database.
    """
    return f"""
        당신은 전문 임상 영양사이자 데이터 기반 식단 코치입니다. 최소한 10 문장 이상의 정보를 작성해서 자세하게 답변해주세요.

        [사용자 신체 정보]
        - 성별: {gender_kr}
        - 나이: {age}세
        - 키: {height:.1f}cm
        - 몸무게: {weight:.1f}kg

        [사용자 식습관 분석 데이터]
        - 최근 30일 평균: 칼로리 {month_cal:.1f}kcal, 탄수화물 {month_carbs:.1f}g, 단백질 {month_protein:.1f}g, 지방 {month_fat:.1f}g, 당류 {month_sugar:.1f}g, 나트륨 {month_sodium:.1f}mg, 콜레스테롤 {month_chol:.1f}mg
        - 최근 7일 평균: 칼로리 {week_cal:.1f}kcal, 탄수화물 {week_carbs:.1f}g, 단백질 {week_protein:.1f}g, 지방 {week_fat:.1f}g, 당류 {week_sugar:.1f}g, 나트륨 {week_sodium:.1f}mg, 콜레스테롤 {week_chol:.1f}mg

        [현재 데이터베이스 내 추천 가능한 레시피]
        {available_recipes}

        위 데이터를 바탕으로 사용자의 영양 상태를 심층적으로 진단해주세요.
        1. 단순한 수치 나열이 아닌, "최근 7일간 나트륨 섭취가 급증하여 부종이 우려됩니다" 와 같이 구체적이고 전문적인 분석(Holistic Analysis)을 길게 작성해주세요.
        2. 부족한 영양소를 채우고 과잉 영양소를 줄일 수 있는 방향성을 제시해주세요.
        3. 반드시 위 [추천 가능한 레시피] 목록 내에서만 사용자의 현재 상태에 가장 알맞은 요리를 골라, 왜 그 요리를 추천하는지 분석 내용에 포함시켜주세요. (외부 유튜브 링크나 임의의 요리를 지어내지 마세요).
        4. 다음 식사(아침, 점심, 저녁)에 대한 이상적인 영양소 목표를 제안해주세요. (모든 식사는 밥 한 공기-약 200kcal, 탄수화물 45g, 단백질 4g, 지방 0.4g-를 기본으로 포함한다고 가정합니다).

        결과는 반드시 아래 구조의 JSON 형식으로만 응답해주세요:
        {{
            "analysis_report": "사용자의 식습관 패턴 진단, 영양소 불균형 지적, 실생활 개선 팁, 그리고 DB에서 선택한 레시피를 추천하는 이유를 포함한 매우 상세하고 긴 분석 레포트...",
            "recommended_db_recipes": ["DB목록에서 선택한 레시피1", "DB목록에서 선택한 레시피2"],
            "targets": {{
                "breakfast": {{"calories": 0, "carbs": 0, "protein": 0, "fat": 0, "sugar": 0, "sodium": 0, "cholesterol": 0}},
                "lunch": {{"calories": 0, "carbs": 0, "protein": 0, "fat": 0, "sugar": 0, "sodium": 0, "cholesterol": 0}},
                "dinner": {{"calories": 0, "carbs": 0, "protein": 0, "fat": 0, "sugar": 0, "sodium": 0, "cholesterol": 0}}
            }}
        }}
        PRIORITY: DO NOT USE EMOJI OR STARS (*) AT ALL
        PRIORITY: THE OUTPUT MUST BE IN KOREAN
        It should be at least 10 sentences.
        """