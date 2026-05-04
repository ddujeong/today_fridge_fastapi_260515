# 패키지(OCR 우선) 식재료 후보 — 팀 검토용

**상태**: 웹 자동수집 제외 **활성화** (`excludeFromWebFetch: true`, 85+25=110 클래스)  
**기계可读 목록**: `app/models/ingredient/data/packaged_ingredient_proposal.json`  
**갱신 방법**: `model_label_to_master.json` 기준으로 `python app/models/ingredient/tools/gen_packaged_ingredient_proposal.py`

## 정의 (초안)

실사용 사진에서 **브랜드 라벨·용기(병·통·튜브·캔·팩 등)**가 식별의 핵이 될 가능성이 높은 품목을 모았다. 파이프라인상 1차 라우트 `packaged_food` → OCR(`packagedFoodOcr`)과 정합되도록 하는 것이 목적이다. **최종 확정 전에는 법적 정의가 아니다.**

## 포함 기준

1. DB `categorySuggestion`가 **소스** 또는 **유제품**인 항목 전부.
2. 그 외 **병입 유·조미유**(들기름, 참기름, 식용유, 해바라기유, 부침유).
3. **캔·햄·소시지·통조림·가공육**(스팸, 리챔, 햄류, 치킨너겟, 미니 돈까스 등).
4. **봉지·판매 단위**가 강한 품목(어묵, 크래미·맛살, 라이스페이퍼, 시판 두부·유부, 스위트콘 등).
5. **꿀·물엿·요리당**, **액상·병 조미/술**(소주·술·배즙·양파즙 등) — 촬영 맥락이 포장 단위에 치우치는 경우가 많다고 가정.

## 제외 후보 (borderline)

가루·알갱이·소금·설탕·깨류·전분·밀가루 계열 등은 **덜어낸 상태** 사진과 **포장 단위**가 섞이기 쉬워 `borderline_for_team`에 두었다. 팀에서 raw 유지 vs OCR로 넘길지 합의한다.

## 개수

- **제안 패키지 클래스**: 85개 (`proposed_packaged`)
- **경계선 검토**: 25개 (`borderline_for_team`)

## 웹 이미지 수집 제외 (확정 후)

1. JSON에서 `"excludeFromWebFetch": true` 로 바꾸면 `fetch_ingredient_images_web.py`가 위 85개 `ing_*` 폴더를 건너뛴다.
2. JSON 수정 없이 시험하려면:  
   `python app/models/ingredient/tools/fetch_ingredient_images_web.py --apply-packaged-exclude`

검토 후 `proposed_packaged` 배열에서 항목을 빼거나 옮기고, 필요하면 `gen_packaged_ingredient_proposal.py`의 `EXTRA` / `BORDERLINE` 집합을 조정해 재생성한다.

## 레시피 적재·정규화와 `ingredient_master`

`app/crawler/import_recipe_csvs_to_postgres_v3.py` → `del_deduplicated_recipes.py` → `normalize.sql` 순으로 돌리거나, **`apply/` 자동 파이프라인**(`n1_import_recipe_csvs_to_postgres_v3.py` → `n2_normalize_aggressive.sql` → `run_n3_normalize_embedding.py`)을 쓰면 **`today_fridge.ingredient_master`가 병합·삭제·갱신**된다. 후자는 특히 공격적 병합 + CSV 승인 쌍 병합이라 로컬 JSON·클래스와 어긋나기 쉽다.

**로컬 작업 기준 DB를 이 파이프라인까지 돌린 상태로 맞출 것**(2026-05-01 기준 팀 워크스페이스에서 `n2`+`n3` 실행됨). 이 문서·`model_label_to_master.json`·YOLO 클래스·웹 수집 제외 목록은 **DB와 따로 놀지 않도록** 재동기화하거나 팀 기준 DB를 사용한다. 절차 요약은 `app/crawler/README.md`를 본다.

**비포장 122클래스 전용 이미지·YOLO 범위**는 `INGREDIENT_ML_TRAINING_SCOPE.md`와 `data/model_label_to_master_train_non_packaged.json`을 본다 (팀 확정 txt 기준; 풀 607행과 별개).
