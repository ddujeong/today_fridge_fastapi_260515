# 식재료 이미지·YOLO 학습 범위 (비포장 확정 122 클래스)

## 팀 확정 리스트

- 원본: `data/ingredients_list_without_package.txt` (125줄, **고유 이름 124개** — `무` 중복 1회)
- **YOLO/이미지 수집에 쓰는 클래스 수: 122** (`distinctIngredientIds` in manifest)
  - 같은 `ingredient_master` 행을 가리키는 팀 표기가 있음 (예: **알배추·배추 → `ing_00115`**, **홍고추·붉은고추 → `ing_01762`**, **계란 → 달걀 `ing_00023`**).
- DB에 없던 **`호박`**, **`완두콩`** 은 `ingredient_master`에 **추가 INSERT** 됨 (`build_non_packaged_train_allowlist.py --apply-inserts`). 새 ID는 manifest JSON에 기록됨.

## 이전 상태 vs 현재 (`ingredient_master`)

| 구분 | 예전 (이미지 수집·초기 YOLO 작업 시) | 현재 |
|------|--------------------------------------|------|
| 행 수 | 대략 수백~수천(레시피 적재·정규화 전) | **609** (비포장 2종 INSERT 후; 기존 607+2) |
| 정규화 | 보수적 `normalize.sql`만 또는 중간 스냅샷 | **`n1` 적재 + `n2` 공격적 병합 + `n3` CSV 승인 병합** 완료 |
| `normalized_name` | 옛 스냅샷과 **ID·이름 불일치** 가능 | 레시피 파이프라인 반영 후 기준 |
| `model_label_to_master.json` (풀) | `generatedAt` 2026-04-30 등 옛 export | **전체 DB export는 별도 갱신** 권장 (`export_yolo_label_assets_from_db.py`) |

**중요:** 예전 `ing_XXXXX` 폴더·옛 JSON은 **현재 DB와 1:1이 아닐 수 있음**. 비포장 학습은 **`model_label_to_master_train_non_packaged.json`** 만 사용한다.

## 레포 산출물 (122 클래스 전용)

| 파일 | 설명 |
|------|------|
| `data/ingredient_non_packaged_allowlist_resolved.json` | 팀 이름 → `ingredient_id`, `model_folder`, 수동 매핑 설명 |
| `data/model_label_to_master_train_non_packaged.json` | YOLO 클래스 키 (`ing_XXXXX`) 122개 |
| `data/ingredient_normalized_vocab_train_non_packaged.json` | 동일 범위 vocab |
| `data/ingredient_image_search_aliases_train_non_packaged.json` | DDGS 수집용 별칭/영문 검색어 |
| `data/ing_train_non_packaged_only_folders.txt` | `fetch_ingredient_images_web.py --only-folders-file` 입력 |

## 웹 이미지 수집 (122만)

```bash
# backend2 루트
python app/models/ingredient/tools/fetch_ingredient_images_web.py \
  --aliases-json app/models/ingredient/data/ingredient_image_search_aliases_train_non_packaged.json \
  --only-folders-file app/models/ingredient/data/ing_train_non_packaged_only_folders.txt \
  --out-root data_sources/team_uploads \
  --max-per-class 100 \
  --target-per-class 100
```

(패키지 제외는 이 allowlist가 이미 비포장만 포함하므로 보통 `--apply-packaged-exclude` 불필요.)

## 데이터셋 조립 → 학습

웹 수집이 끝난 **뒤** 조립하는 것이 좋다. `train/` 아래에 없는 `ing_*` 클래스가 있으면 Ultralytics가 **실제 이미지가 있는 클래스 수만** (`nc`) 잡고, `val/` 클래스 수가 맞지 않으면 경고가 난다. **122개 전부** 쓰려면 fetch 후 `train/ing_XXXXX`가 모두 생겼는지 확인하고 다시 assemble한다.

```bash
python app/models/ingredient/tools/assemble_ingredient_master_cls_dataset.py \
  --master-json app/models/ingredient/data/model_label_to_master_train_non_packaged.json \
  --team-root data_sources/team_uploads \
  --out ml_datasets/ingredient_master_cls_train_non_packaged \
  --mode copy

yolo classify train model=yolov8n-cls.pt data=ml_datasets/ingredient_master_cls_train_non_packaged \
  epochs=80 imgsz=224 batch=16 device=0 name=ing_non_packaged_122
```

`val/`·`test/`에 오래된 다른 실험 폴더가 남아 있으면 클래스 수가 어긋난다. 필요 시 해당 디렉터리를 비우거나, `train`에서 비율 분할 스크립트로 다시 만든다.

## 스크립트

- `tools/build_non_packaged_train_allowlist.py` — 팀 txt → manifest, (옵션) INSERT
- `tools/export_yolo_label_assets_from_db.py` — `--manifest-json` + `--label-map-filename` 로 서브셋 export
