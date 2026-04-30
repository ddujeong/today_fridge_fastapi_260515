"""One-off helper: build packaged_ingredient_proposal.json from model_label_to_master.json."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data"
LABELS_PATH = ROOT / "model_label_to_master.json"
OUT_PATH = ROOT / "packaged_ingredient_proposal.json"

# Retail bottle/tube/can/pouch — OCR route가 유리한 품목 (소스·유제품 외 추가)
EXTRA: set[str] = {
    "ing_00014",  # 들기름
    "ing_00022",  # 어묵 (봉지·판매 단위)
    "ing_00038",  # 참기름
    "ing_00042",  # 식용유
    "ing_00056",  # 두부
    "ing_00066",  # 소시지
    "ing_00106",  # 베이컨
    "ing_00109",  # 라이스페이퍼
    "ing_00122",  # 스팸
    "ing_00129",  # 맛살
    "ing_00152",  # 크래미
    "ing_00157",  # 햄
    "ing_00167",  # 꿀
    "ing_00168",  # 진미채 (포장 건어물)
    "ing_00169",  # 치킨너겟
    "ing_00201",  # 젓갈
    "ing_00240",  # 미니 돈까스
    "ing_00291",  # 단단한 두부
    "ing_00313",  # 밥새우
    "ing_00329",  # 시판네모유부
    "ing_00332",  # 스위트콘
    "ing_00343",  # 꿀/물엿
    "ing_00351",  # 배즙
    "ing_00361",  # 소주
    "ing_00371",  # 술
    "ing_00498",  # 와사비
    "ing_00556",  # 게맛살
    "ing_00559",  # 머스터드소스
    "ing_00567",  # 캐찹
    "ing_00669",  # 해바라기유
    "ing_00712",  # 리챔
    "ing_00864",  # 어른치즈
    "ing_00896",  # 체더치즈
    "ing_00948",  # 뉴슈가
    "ing_00951",  # 새우젓
    "ing_00952",  # 양파즙
    "ing_01125",  # 냉장햄
    "ing_01126",  # 통조림햄
    "ing_01172",  # 부침유
    "ing_01188",  # 통조림참치
    "ing_01190",  # 케챱
    "ing_01275",  # 캔햄
    "ing_01390",  # 슬라이스햄
    "ing_01391",  # 소세지
    "ing_01439",  # 꽁치통조림
}

# 가루·알갱이·물 등: 마트 포장 vs 덜어낸 상태가 섞여 raw 학습 가치 있음 → 팀 판단
BORDERLINE: set[str] = {
    "ing_00002",  # 가루
    "ing_00003",  # 물
    "ing_00005",  # 소금
    "ing_00021",  # 설탕
    "ing_00031",  # 통깨
    "ing_00035",  # 깨소금
    "ing_00045",  # 검은깨
    "ing_00059",  # 깨
    "ing_00088",  # 페퍼론치노 (통조림 vs 건조 고추)
    "ing_00133",  # 파슬리가루
    "ing_00138",  # 들깨가루
    "ing_00166",  # 연겨자
    "ing_00179",  # 전분
    "ing_00188",  # 생강가루
    "ing_00223",  # 참깨
    "ing_00233",  # 전분가루
    "ing_00321",  # 부침가루(밀가루)
    "ing_00327",  # 감자전분
    "ing_00387",  # 깨 간 것
    "ing_00485",  # 찹쌀가루
    "ing_00947",  # 햇마늘 — 원물에 가까움 (제외 유지)
    "ing_01171",  # 쌀부침가루
    "ing_01267",  # 간 깨
    "ing_01378",  # 멸치 다시마 육수 — 티백·액상 포장 혼재
    "ing_01441",  # 김치국물 — 용기·포장 혼재
}


def main() -> None:
    doc = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    labels: dict = doc["labels"]
    proposed: dict[str, dict] = {}
    for key, meta in labels.items():
        cat = meta.get("categorySuggestion") or ""
        if key in BORDERLINE:
            continue
        reason = ""
        if cat in ("소스", "유제품"):
            reason = f"DB category `{cat}` → 병·통·튜브 등 유통상품 비중 높음"
            proposed[key] = {**meta, "model_folder": key, "proposal_reason": reason}
        elif key in EXTRA:
            reason = "소스/유제품 외: 캔·봉지·병입 유통 단위로 촬영될 가능성이 높아 OCR 라우트 후보"
            proposed[key] = {**meta, "model_folder": key, "proposal_reason": reason}

    borderline_entries = []
    for key in sorted(BORDERLINE):
        if key in labels:
            m = labels[key]
            borderline_entries.append(
                {
                    "model_folder": key,
                    "ingredientId": m.get("ingredientId"),
                    "normalizedName": m.get("normalizedName"),
                    "categorySuggestion": m.get("categorySuggestion"),
                    "note": "가정용 덜어낸 상태·벌크 사진과 포장 단위가 섞일 수 있어 팀 합의 필요",
                }
            )

    prev_exclude = False
    if OUT_PATH.is_file():
        try:
            prev = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            prev_exclude = bool(prev.get("excludeFromWebFetch"))
        except Exception:
            prev_exclude = False

    out = {
        "schema": "packaged_ingredient_proposal_v1",
        "status": "TEAM_REVIEW",
        "excludeFromWebFetch": prev_exclude,
        "excludeFromWebFetch_note": (
            "팀 확정 후 true로 바꾸면 fetch_ingredient_images_web.py가 proposed_packaged 폴더를 기본 제외한다. "
            "CLI만: --apply-packaged-exclude"
        ),
        "generatedFrom": str(LABELS_PATH.name),
        "definition": (
            "‘패키지(OCR 우선)’ 후보: 실사용 사진에서 **브랜드 라벨·용기(병·통·튜브·캔·비닐·팩)**가 "
            "식별의 핵이 되는 식품. 1차 라우터의 `packaged_food`와 정합되도록 잡은 초안이며, "
            "최종 확정 전까지는 이미지 수집 제외에만 사용한다."
        ),
        "counts": {
            "proposed_packaged": len(proposed),
            "borderline": len(borderline_entries),
        },
        "proposed_packaged": sorted(
            (
                {
                    "model_folder": k,
                    "ingredientId": v.get("ingredientId"),
                    "normalizedName": v.get("normalizedName"),
                    "displayName": v.get("displayName"),
                    "categorySuggestion": v.get("categorySuggestion"),
                    "proposal_reason": v.get("proposal_reason"),
                }
                for k, v in proposed.items()
            ),
            key=lambda x: x["model_folder"],
        ),
        "borderline_for_team": borderline_entries,
        "not_in_this_list": (
            "신선 채소·과일·버섯, 원물 육류·생선, 깐 달걀·메추리알, 풀·잎 채소, "
            "다진 채소(조리 형태) 등은 기본적으로 raw_ingredient 학습 대상으로 둔다."
        ),
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(proposed)} proposed, {len(borderline_entries)} borderline)")


if __name__ == "__main__":
    main()
