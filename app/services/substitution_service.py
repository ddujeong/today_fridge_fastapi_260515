from app.schemas.substitution_llm import (
    SubstitutionLlmRequest,
    SubstitutionLlmResponse,
    SubstitutionLlmResult,
)


def suggest_substitutions(request: SubstitutionLlmRequest) -> SubstitutionLlmResponse:
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
    optional_keywords = ["깨", "후추", "고명", "쪽파", "대파"]

    return any(keyword in missing for keyword in optional_keywords)