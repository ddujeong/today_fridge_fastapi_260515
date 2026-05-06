import json
import re
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ollama_service import OllamaService
from app.services.gemini_service import GeminiService

router = APIRouter(prefix="/internal/recipe-tags", tags=["recipe-tags"])

ollama_service = OllamaService()
gemini_service = GeminiService()

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

아래 레시피를 보고 태그를 분류해라.

조리 타입은 반드시 하나만 선택한다.
스타일 태그는 0개에서 최대 2개까지 선택한다.

COOKING_TYPE 선택지:
- SOUP: 국/탕
- STEW: 찌개/전골
- STIR_FRY: 볶음
- BRAISED: 조림
- SEASONED: 무침
- PANCAKE: 전/부침개
- UNKNOWN: 위 분류에 해당하지 않음

STYLE 선택지:
- SPICY: 매운맛
- LIGHT: 담백한/가벼운
- REFRESHING: 시원한/상큼한
- SAVORY: 감칠맛/짭짤한
- SWEET: 단맛

판단 규칙:
- "떡국떡"은 재료명이므로 SOUP으로 분류하지 않는다.
- "국민", "중국식"에 포함된 "국"은 SOUP 의미가 아니다.
- "전복"의 "전"은 PANCAKE 의미가 아니다.
- 제목만 보지 말고 재료와 요약도 함께 판단한다.
- 애매하면 COOKING_TYPE은 UNKNOWN을 선택한다.
- STYLE은 확실할 때만 선택한다.
- 콩국수, 냉면, 비빔면, 라면, 우동, 칼국수처럼 면 요리는 SOUP이 아니다. UNKNOWN으로 분류한다.
- 말이, 찜, 부침, 전, 까스, 스테이크, 덮밥은 SOUP이 아니다.
- 반드시 JSON만 반환한다.

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
def validate_cooking_type(title: str, tag_code: str) -> bool:
    title = title or ""

    soup_exclude_keywords = [
        "국수", "찜", "말이", "부침", "전", "까스",
        "스테이크", "덮밥", "볶음", "조림", "튀김", "샐러드"
    ]

    if tag_code == "SOUP":
        if any(keyword in title for keyword in soup_exclude_keywords):
            return False

        soup_include_keywords = ["국", "탕", "냉국"]
        if not any(keyword in title for keyword in soup_include_keywords):
            return False

    return True

@router.post("/classify", response_model=RecipeTagClassifyResponse)
def classify_recipe_tags(req: RecipeTagClassifyRequest):
    try:
        prompt = build_prompt(req)

        # raw = ollama_service.generate(prompt)
        raw = gemini_service.generate(prompt)
        parsed = extract_json(raw)

        result_tags = []

        for tag in parsed.get("tags", []):
            tag_type = str(tag.get("tagType", "")).upper()
            tag_code = str(tag.get("tagCode", "")).upper()
            confidence = float(tag.get("confidence", 0.7))

            if tag_type == "COOKING_TYPE":
                if tag_code not in VALID_COOKING_TAGS or tag_code == "UNKNOWN":
                    continue
                if not validate_cooking_type(req.title, tag_code):
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