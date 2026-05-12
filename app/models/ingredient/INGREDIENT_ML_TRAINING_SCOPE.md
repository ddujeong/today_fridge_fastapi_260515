# 식재료 이미지·YOLO 학습 범위 (비포장)

## 단일 기준 (SSOT)

**팀 공용 DB(Neon)의 `today_fridge.ingredient_master` + `ingredient_category`가 최종 기준이다.**  
레포에 있는 JSON·문서·클래스 개수는 “과거 스냅샷”일 수 있으며, **DB 스키마/데이터가 바뀌면 아래 export로 레포를 DB에 맞출 것.**

권장 절차 (Neon에 붙는 환경에서):

```powershell
$env:DB_URL="jdbc:postgresql://<호스트>/neondb?sslmode=require"
$env:DB_USERNAME="..."
$env:DB_PASSWORD="..."
Set-Location <project_final_backend_2>
python app/models/ingredient/tools/export_train_labels_from_db.py
python app/models/ingredient/tools/build_train_class_reference.py
```

- `export_train_labels_from_db.py`: 현재 JSON에 나온 `ingredient_id`들을 DB에서 조회해 **`displayName` / `normalizedName` / 카테고리 표시명을 DB 값으로 덮어쓴다.** DB에 없는 ID는 **기본적으로 JSON에서 제거(prune)** 한다 (`--no-prune`로 예외 가능).
- **`ingredient_master`에 행을 INSERT해서 맞추지 않는다.** 레포가 DB를 따라간다.

생성·갱신되는 파일 예:

- `data/model_label_to_master_train_non_packaged.json` — 학습 라벨 매핑 (클래스 개수는 DB와 동기화 후 가변)
- `data/train_class_reference*.csv|.md|.txt` — 폴더·라벨 참조표 (`train_folder_orphans_on_disk.txt`에 디스크만 남은 폴더 목록)

## 과거 참고 자료 (고정 숫자 아님)

| 자료 | 역할 |
|------|------|
| `data/ingredients_list_without_package.txt` | 초기 기획 시 팀이 나열한 목록 (125줄 등 **역사적** 숫자) |
| `data/ingredient_non_packaged_allowlist_resolved.json` | 그 시점의 이름→ID 매핑 스냅샷; **현재 DB와 개수·행이 다를 수 있음** |

학습에 쓰는 공식 라벨 파일은 **`model_label_to_master_train_non_packaged.json`** 이고, 내용은 위 export로 갱신한다.

## 데이터셋·학습 스크립트

이전 문서의 “122 클래스 고정” 같은 표현은 폐기한다. **`model_label_to_master_train_non_packaged.json`에 남은 키 수 = 현재 동기화된 클래스 수.**

```bash
python app/models/ingredient/tools/assemble_ingredient_master_cls_dataset.py \
  --master-json app/models/ingredient/data/model_label_to_master_train_non_packaged.json \
  --team-root data_sources/team_uploads \
  --out ml_datasets/ingredient_master_cls_train_non_packaged \
  --mode copy
```

부가 산출물(`ingredient_normalized_vocab_train_non_packaged.json`, `ingredient_image_search_aliases_train_non_packaged.json` 등)의 행 수·내용은 DB 변경 후 **`export_yolo_label_assets_from_db.py` 등으로 재생성**하는 것이 안전하다.

## “DB에 없음”처럼 보일 때 (다른 ID·이름으로 들어간 경우)

일부 `ingredient_id`는 PK로는 없지만, **병합·정규화·별칭(alias_text)** 때문에 **다른 행 ID**로 존재할 수 있다.

`export` 전에(또는 prune 하기 전 백업 JSON으로) 후보 조회:

```bash
python app/models/ingredient/tools/find_db_candidates_for_missing_train_ids.py
```

결과는 `data/missing_train_id_db_candidates.tsv` — 수동 검토 후 폴더명(`ing_XXXXX`)·JSON 키를 실제 DB ID에 맞출지 결정한다.

## 관련 도구

- `tools/export_train_labels_from_db.py` — Neon SSOT → 학습용 JSON 정렬
- `tools/build_train_class_reference.py` — 참조표·고아 폴더 목록
- `tools/find_db_candidates_for_missing_train_ids.py` — 누락된 PK에 대한 DB 후보 행 검색
- `tools/export_yolo_label_assets_from_db.py` — YOLO 자산 전체 export (서브셋 옵션)

---

## 폴더명 ↔ 재료명(DB) 매칭 파일 위치 (현재 Neon 기준 갱신 후)

| 용도 | 경로 |
|------|------|
| **공식 라벨 맵** (클래스 `ing_XXXXX` → `ingredientId`, 표시명·정규화명·카테고리) | `app/models/ingredient/data/model_label_to_master_train_non_packaged.json` |
| **인덱스↔이름 참조표** (Markdown / 간단 텍스트) | `app/models/ingredient/data/train_class_reference.md`, `train_class_reference_simple.txt` |
| **CSV 참조표** (동일 내용; Excel 잠금 시 `_train_ref_gen_out/train_class_reference.csv`) | `_train_ref_gen_out/train_class_reference.csv` 또는 `data/train_class_reference.csv` |
| **디스크에만 있는 train 클래스 폴더** (고아 목록) | `data/train_folder_orphans_on_disk.txt` (있을 때만; `build_train_class_reference.py` 생성) |
| **재학습 전 예전 YOLO 클래스명 → 현재 `ing_*`** (임시) | `app/models/ingredient/data/yolo_legacy_model_label_remap.json` |

갱신 명령은 상단 PowerShell 블록의 `export_train_labels_from_db.py` → `build_train_class_reference.py` 순서를 따른다.

---

## 재학습 전 임시 완화 (YOLO·Neon ID 불일치 대비)

Neon PK 정리로 **클래스 폴더/JSON ID를 바꾼 뒤** 아직 `best.pt`를 다시 학습하지 않은 경우:

1. **레거시 클래스명 치환** — `yolo_legacy_model_label_remap.json` + `rawIngredientClassifier`의 `RAW_INGREDIENT_LEGACY_REMAP` (모델이 예전 `ing_*`를 내도 DB 매칭용 키로 조회).
2. **TTA** — `RAW_INGREDIENT_TTA=1` 시 좌우 반전 추론 후 클래스 확률 평균(오분류 완화·추론 시간 증가).
3. **불확실 표시** — 1·2위 확률 차·1위 절대 신뢰도가 낮으면 `predictionUncertain=true`, Vision 응답에서 `needsReview`와 연동.

완전히 “틀린 클래스를 고른 경우”를 확률만으로 바로잡는 것은 불가능에 가깝고, 위 조합은 **완화 + 사람 검토 유도**에 가깝다.

---

## YOLO 재학습 후 정리 (임시 조치 제거 체크리스트)

새 데이터셋으로 **`ing_*` 폴더명 = 현재 DB PK**에 맞춰 재학습하고 `raw_ingredient_best.pt`를 배포한 뒤:

1. **`yolo_legacy_model_label_remap.json` 제거** 또는 빈 `{"remap":{}}` — 모델 출력이 이미 현재 키와 일치하는지 확인 후 삭제.
2. **환경 변수** — `RAW_INGREDIENT_LEGACY_REMAP=0`, `RAW_INGREDIENT_TTA=0`(성능 우선 시).
3. **`export_train_labels_from_db.py` + `build_train_class_reference.py`** 로 JSON·참조표만 최신 Neon과 맞으면 됨.
4. **`rawIngredientClassifier.py`** 안의 레거시/TTA/불확실 로직은 파일 없음·`LEGACY_REMAP=0`이면 사실상 무시되므로 필수 삭제는 아님; 유지해도 동작은 “공식 재학습 후”와 호환된다.

이 체크리스트를 적용한 뒤에는 **임시 대응 없이** 폴더명·라벨 JSON·가중치가 한 줄로 맞는 상태가 된다.
