import json
import re
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ollama_service import OllamaService

router = APIRouter(prefix="/internal/recipe-tags", tags=["recipe-tags"])

ollama_service = OllamaService()


class RecipeTagClassifyRequest(BaseModel):
    recipeId: int
    title: str
    ingredients: List[str] = []
    summary: Optional[str] = None


class RecipeTagDto(BaseModel):
    tagType: str
    tagCode: str
    confidence: float
    sourceType: str


class RecipeTagClassifyResponse(BaseModel):
    recipeId: int
    tags: List[RecipeTagDto]


VALID_COOKING_TAGS = {
    "SOUP",
    "STEW",
    "STIR_FRY",
    "BRAISED",
    "SEASONED",
    "PANCAKE",
    "UNKNOWN",
}

VALID_STYLE_TAGS = {
    "SPICY",
    "LIGHT",
    "REFRESHING",
    "SAVORY",
    "SWEET",
}


def build_prompt(req: RecipeTagClassifyRequest) -> str:
    ingredients = ", ".join(req.ingredients or [])

    return f"""
너는 한국 요리 레시피 태그 분류기다.

아래 레시피를 보고 COOKING_TYPE과 STYLE 태그를 분류해라.

분류 원칙:
- COOKING_TYPE은 반드시 하나만 판단한다.
- STYLE 태그는 0개에서 최대 2개까지 선택한다.
- 확실하지 않으면 COOKING_TYPE은 UNKNOWN으로 둔다.
- 억지로 비슷한 조리 타입에 끼워 넣지 않는다.
- 반드시 JSON만 반환한다.

COOKING_TYPE 선택지:
- SOUP: 국, 탕, 냉국처럼 국물이 주된 요리
- STEW: 찌개, 전골처럼 국물이 있지만 건더기가 많고 진한 요리
- STIR_FRY: 볶음 요리
- BRAISED: 조림 요리
- SEASONED: 무침 요리
- PANCAKE: 전, 부침개 요리
- UNKNOWN: 위 분류에 명확히 해당하지 않는 요리

STYLE 선택지:
- SPICY: 매운맛, 얼큰한 맛
- LIGHT: 담백한/가벼운
- REFRESHING: 시원한/상큼한
- SAVORY: 감칠맛/짭짤한
- SWEET: 단맛

중요한 예외 규칙:
- 계란찜, 달걀찜, 찜 요리는 SOUP이 아니다. UNKNOWN으로 분류한다.
- 맛탕, 튀김, 구이, 샐러드, 면 요리, 디저트류는 명확한 키워드가 없으면 UNKNOWN으로 분류한다.
- "떡국떡"은 재료명이므로 SOUP으로 분류하지 않는다.
- "국민", "중국식", "미국식"에 포함된 "국"은 SOUP 의미가 아니다.
- "전복"의 "전"은 PANCAKE 의미가 아니다.
- "볶음김치", "감자볶음", "어묵볶음"처럼 제목에 볶음이 명확하면 STIR_FRY다.
- "조림"이 제목에 명확하면 BRAISED다.
- "무침"이 제목에 명확하면 SEASONED다.
- "국", "탕", "냉국"이 요리명으로 명확하면 SOUP이다.
- "찌개", "전골"이 요리명으로 명확하면 STEW다.
- 제목만 보지 말고 재료와 요약도 함께 판단한다.
- STYLE은 확실할 때만 선택한다.

레시피:
title: {req.title}
summary: {req.summary or ""}
ingredients: {ingredients}

반환 형식:
{{
  "tags": [
    {{"tagType":"COOKING_TYPE","tagCode":"SOUP","confidence":0.9}},
    {{"tagType":"STYLE","tagCode":"REFRESHING","confidence":0.8}}
  ]
}}
""".strip()


def extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        raise ValueError("LLM 응답에서 JSON을 찾을 수 없습니다.")

    return json.loads(match.group())


@router.post("/classify", response_model=RecipeTagClassifyResponse)
def classify_recipe_tags(req: RecipeTagClassifyRequest):
    try:
        prompt = build_prompt(req)

        raw = ollama_service.generate(prompt)
        parsed = extract_json(raw)

        result_tags = []

        for tag in parsed.get("tags", []):
            tag_type = str(tag.get("tagType", "")).upper()
            tag_code = str(tag.get("tagCode", "")).upper()
            confidence = float(tag.get("confidence", 0.7))

            if tag_type == "COOKING_TYPE":
                if tag_code not in VALID_COOKING_TAGS or tag_code == "UNKNOWN":
                    continue

            elif tag_type == "STYLE":
                if tag_code not in VALID_STYLE_TAGS:
                    continue

            else:
                continue

            result_tags.append(
                RecipeTagDto(
                    tagType=tag_type,
                    tagCode=tag_code,
                    confidence=round(confidence, 4),
                    sourceType="LLM",
                )
            )

        return RecipeTagClassifyResponse(
            recipeId=req.recipeId,
            tags=result_tags
        )

    except Exception as e:
        print(f"[recipe-tag] classify failed recipeId={req.recipeId}, error={e}")

        return RecipeTagClassifyResponse(
            recipeId=req.recipeId,
            tags=[]
        )