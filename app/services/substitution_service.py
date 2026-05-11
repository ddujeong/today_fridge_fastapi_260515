import json
import re

from app.schemas.substitution_llm import (
    SubstitutionLlmRequest,
    SubstitutionLlmResponse,
    SubstitutionLlmResult,
)
from app.services.gemini_service import GeminiService

gemini_service = GeminiService()


def suggest_substitutions(request: SubstitutionLlmRequest) -> SubstitutionLlmResponse:
    try:
        prompt = build_substitution_prompt(request)
        response_text = gemini_service.generate(prompt)
        parsed = extract_json(response_text)

        results = [
            SubstitutionLlmResult(**item)
            for item in parsed.get("results", [])
        ]

        return validate_response(results, request)

    except Exception as e:
        print(f"[SUBSTITUTION_LLM_FALLBACK] {e}")
        return suggest_substitutions_by_rule(request)


def build_substitution_prompt(request: SubstitutionLlmRequest) -> str:
    return f"""
너는 레시피의 부족 재료에 대해 대체 가능성 또는 생략 가능성을 판단하는 시스템이다.

[레시피명]
{request.recipeTitle}

[레시피에 필요한 재료]
{json.dumps(request.recipeIngredients, ensure_ascii=False)}

[사용자가 보유한 재료]
{json.dumps(request.ownedIngredients, ensure_ascii=False)}

[부족한 재료]
{json.dumps(request.missingIngredients, ensure_ascii=False)}

[판단 기준]
- 부족한 재료마다 반드시 하나의 결과를 만든다.
- decisionType은 반드시 아래 셋 중 하나만 사용한다.
  1. SUBSTITUTE_AVAILABLE: 사용자가 보유한 재료 중 대체 가능한 재료가 있음
  2. OPTIONAL: 대체재는 없지만 생략해도 레시피가 크게 무너지지 않음
  3. REQUIRED: 대체도 어렵고 생략하면 레시피 완성도가 크게 떨어짐
- substituteIngredient는 반드시 [사용자가 보유한 재료] 중 하나여야 한다.
- 적절한 대체재가 없으면 substituteIngredient는 null이다.
- 사용자가 보유하지 않은 재료를 대체재로 만들지 마라.
- 이유는 한 문장으로 짧게 작성한다.
- 마크다운 없이 JSON만 반환한다.

[중요 예시]
- 카레에서 감자는 OPTIONAL일 수 있다.
- 카레가루는 REQUIRED이다.
- 전 요리에서 부침가루는 밀가루로 대체 가능할 수 있다.
- 소금, 후추, 깨, 고명류는 대체로 OPTIONAL일 수 있다.
- 주재료는 REQUIRED에 가깝다.

[응답 JSON 형식]
{{
  "results": [
    {{
      "missingIngredient": "부족재료명",
      "decisionType": "SUBSTITUTE_AVAILABLE",
      "substituteIngredient": "보유재료명",
      "reason": "짧은 이유"
    }},
    {{
      "missingIngredient": "부족재료명",
      "decisionType": "OPTIONAL",
      "substituteIngredient": null,
      "reason": "짧은 이유"
    }},
    {{
      "missingIngredient": "부족재료명",
      "decisionType": "REQUIRED",
      "substituteIngredient": null,
      "reason": "짧은 이유"
    }}
  ]
}}
"""


def extract_json(text: str) -> dict:
    cleaned = text.strip()

    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    return json.loads(cleaned)


def validate_response(
    results: list[SubstitutionLlmResult],
    request: SubstitutionLlmRequest,
) -> SubstitutionLlmResponse:
    owned_set = set(request.ownedIngredients)
    missing_set = set(request.missingIngredients)

    validated = []

    for result in results:
        if result.missingIngredient not in missing_set:
            continue

        if result.decisionType == "SUBSTITUTE_AVAILABLE":
            if result.substituteIngredient not in owned_set:
                validated.append(
                    SubstitutionLlmResult(
                        missingIngredient=result.missingIngredient,
                        decisionType="REQUIRED",
                        substituteIngredient=None,
                        reason="보유 재료 안에서 사용할 수 있는 대체재가 확인되지 않았습니다.",
                    )
                )
                continue

        if result.decisionType in ["OPTIONAL", "REQUIRED"]:
            result.substituteIngredient = None

        validated.append(result)

    returned_missing = {r.missingIngredient for r in validated}

    for missing in request.missingIngredients:
        if missing not in returned_missing:
            validated.append(
                SubstitutionLlmResult(
                    missingIngredient=missing,
                    decisionType="REQUIRED",
                    substituteIngredient=None,
                    reason="해당 재료는 레시피 완성에 필요한 재료로 판단됩니다.",
                )
            )

    return SubstitutionLlmResponse(results=validated)


def suggest_substitutions_by_rule(
    request: SubstitutionLlmRequest,
) -> SubstitutionLlmResponse:
    results = []

    for missing in request.missingIngredients:
        substitute = find_owned_substitute(missing, request.ownedIngredients)

        if substitute:
            results.append(
                SubstitutionLlmResult(
                    missingIngredient=missing,
                    decisionType="SUBSTITUTE_AVAILABLE",
                    substituteIngredient=substitute,
                    reason=f"{substitute}는 보유 재료이며, {missing}의 대체 후보로 사용할 수 있습니다.",
                )
            )
        elif is_optional_ingredient(missing):
            results.append(
                SubstitutionLlmResult(
                    missingIngredient=missing,
                    decisionType="OPTIONAL",
                    substituteIngredient=None,
                    reason=f"{missing}은 레시피 완성에 반드시 필요한 핵심 재료는 아니므로 생략 가능성이 있습니다.",
                )
            )
        else:
            results.append(
                SubstitutionLlmResult(
                    missingIngredient=missing,
                    decisionType="REQUIRED",
                    substituteIngredient=None,
                    reason=f"{missing}은 이 레시피에서 대체 또는 생략이 어려운 재료입니다.",
                )
            )

    return SubstitutionLlmResponse(results=results)


def find_owned_substitute(missing: str, owned_ingredients: list[str]) -> str | None:
    simple_rules = {
        "부침가루": ["밀가루"],
        "밀가루": ["부침가루"],
        "소금": ["굵은소금"],
        "설탕": ["올리고당", "꿀"],
    }

    candidates = simple_rules.get(missing, [])

    for candidate in candidates:
        if candidate in owned_ingredients:
            return candidate

    return None


def is_optional_ingredient(missing: str) -> bool:
    optional_keywords = ["깨", "후추", "고명", "쪽파", "대파", "소금"]

    return any(keyword in missing for keyword in optional_keywords)