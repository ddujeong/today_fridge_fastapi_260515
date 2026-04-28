from typing import Optional

# 카테고리 코드 → 키워드 매핑 테이블
# 재료명에 해당 키워드가 포함되면 해당 카테고리로 분류
CATEGORY_KEYWORDS: list[tuple[str, str, list[str]]] = [
    ("MEAT",      "육류",   ["소고기", "돼지고기", "닭고기", "닭", "소", "돼지", "양고기", "오리", "베이컨", "햄", "소시지", "삼겹살", "등심", "안심", "갈비", "불고기", "육류", "스테이크"]),
    ("SEAFOOD",   "해산물", ["생선", "연어", "참치", "고등어", "갈치", "조기", "새우", "오징어", "문어", "낙지", "꽃게", "대게", "가재", "홍합", "굴", "조개", "전복", "해산물", "어류", "어패류", "멸치", "황태", "북어"]),
    ("DAIRY",     "유제품", ["우유", "치즈", "버터", "요거트", "요구르트", "크림", "생크림", "아이스크림", "두유", "유제품"]),
    ("FRUIT",     "과일",   ["사과", "배", "딸기", "포도", "수박", "참외", "복숭아", "자두", "살구", "망고", "파인애플", "키위", "레몬", "오렌지", "귤", "바나나", "블루베리", "체리", "멜론", "과일"]),
    ("VEGETABLE", "채소",   ["당근", "양파", "마늘", "파", "대파", "쪽파", "생강", "감자", "고구마", "배추", "상추", "시금치", "브로콜리", "콜리플라워", "양배추", "오이", "가지", "호박", "애호박", "토마토", "피망", "고추", "파프리카", "버섯", "표고버섯", "느타리버섯", "팽이버섯", "콩나물", "숙주", "두부", "채소", "야채"]),
    ("GRAIN",     "곡류",   ["쌀", "현미", "찹쌀", "보리", "밀", "밀가루", "소면", "라면", "파스타", "스파게티", "우동", "냉면", "국수", "떡", "빵", "식빵", "곡류", "잡곡", "귀리", "옥수수"]),
    ("SEASONING", "조미료", ["소금", "설탕", "간장", "된장", "고추장", "고춧가루", "참기름", "들기름", "식용유", "식초", "후추", "조미료", "다시다", "미원", "굴소스", "피시소스", "올리브유"]),
    ("SAUCE",     "소스",   ["케첩", "마요네즈", "머스타드", "소스", "드레싱", "타바스코", "스리라차", "칠리소스", "바베큐소스", "데리야키"]),
    ("ETC",       "기타",   []),  # fallback
]


def classify_category(name: str) -> dict:
    """
    재료명 키워드 기반 카테고리 자동 분류.
    반환: { category_code, category_name, matched_keyword, confidence }
    """
    name_lower = name.strip().lower()

    for category_code, category_name, keywords in CATEGORY_KEYWORDS:
        if category_code == "ETC":
            continue
        for keyword in keywords:
            if keyword in name_lower:
                return {
                    "category_code": category_code,
                    "category_name": category_name,
                    "matched_keyword": keyword,
                    "confidence": 0.9,
                }

    return {
        "category_code": "ETC",
        "category_name": "기타",
        "matched_keyword": None,
        "confidence": 0.3,
    }
