# rawIngredientClassifier 적용 순서

## 1. 파일 배치

```text
app/models/ingredient/
  rawIngredientClassifier.py
  weights/
    raw_ingredient_best.pt
  tools/
    prepare_raw_ingredient_cls_dataset.py
```

## 2. visionInternalApi.py import 수정

기존 snake_case import가 있다면:

```python
from app.models.ingredient.raw_ingredient_classifier import recognize_raw_ingredient_image
```

아래처럼 변경:

```python
from app.models.ingredient.rawIngredientClassifier import recognize_raw_ingredient_image
```

## 3. raw 식재료 세부 분류 데이터셋 생성

```bash
python app/models/ingredient/tools/prepare_raw_ingredient_cls_dataset.py \
  --source ./data_sources/GroceryStoreDataset/dataset \
  --out ./ml_datasets/raw_ingredient_cls_dataset \
  --mode copy
```

## 4. 학습

```bash
yolo classify train \
  model=yolov8n-cls.pt \
  data=./ml_datasets/raw_ingredient_cls_dataset \
  epochs=40 \
  imgsz=224 \
  batch=16 \
  name=raw_ingredient_v1
```

Mac MPS:

```bash
yolo classify train \
  model=yolov8n-cls.pt \
  data=./ml_datasets/raw_ingredient_cls_dataset \
  epochs=40 \
  imgsz=224 \
  batch=16 \
  device=mps \
  name=raw_ingredient_v1
```

## 5. best.pt 복사

```bash
mkdir -p app/models/ingredient/weights

cp runs/classify/raw_ingredient_v1/weights/best.pt \
  app/models/ingredient/weights/raw_ingredient_best.pt
```

## 6. 단독 테스트

```bash
python app/models/ingredient/rawIngredientClassifier.py \
  --image app/models/img2class/apple.jpg \
  --model app/models/ingredient/weights/raw_ingredient_best.pt \
  --topK 5
```

## 7. 내부 API 테스트

```bash
curl -X POST "http://localhost:8000/internal/v1/vision/recognize-ingredient-image" \
  -H "X-Internal-Service: spring-boot" \
  -H "X-Internal-Token: dev-secret" \
  -H "X-Request-Id: req_local_001" \
  -F "file=@app/models/img2class/apple.jpg" \
  -F "topK=5" \
  -F "detectMultiple=false" \
  -F "source=upload"
```

## 8. OCR은 건드리지 않음

`packaged_food` 경로는 다른 팀원의 `packaged_food_ocr.py`가 담당한다.
이 작업에서는 `raw_ingredient` 경로만 실제 classifier로 교체한다.

## 9. `ingredient_master` 기준 275클래스(또는 전체 행) 학습

흐름은 **이미지 분류(YOLO classify)** 이다. 한 장의 사진이 275개(실제는 DB 행 수) 클래스 중 어디에 가깝다는 **확률 벡터**를 낸다.  
`app/api/internal/visionInternalApi.py` 는 `raw_ingredient` 경로에서 **상위 3개**(`MAX_RECOGNITION_CANDIDATES`, `topK` 폼과 함께 캡)와 `confidence`(0~1)를 내려준다. UI에서는 `confidence * 100`으로 퍼센트 표시하면 된다.

### 9.1 DB에서 라벨 맵·어휘 JSON 생성

PostgreSQL에 동기화된 `ingredient_master` 기준으로 다음 두 파일을 다시 만든다.

```bash
cd project_final_backend_2
set DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/today_fridge
python app/models/ingredient/tools/export_yolo_label_assets_from_db.py --out-dir app/models/ingredient/data
```

선택: `--active-only` 로 `is_active = false` 행 제외.

- 출력 `model_label_to_master.json`: 클래스 키는 **`ing_00042`처럼 ingredient_id 기준 zero-padding** (폴더명 정렬이 숫자 순서와 같아지도록).
- 각 항목에 `ingredientId`(PK) 포함 → 추론 결과에 `ingredientMasterId`로 전달되어 사용자가 고를 때 마스터 행을 바로 지정 가능.

### 9.2 학습용 이미지 폴더 규칙 (원격 GPU 서버 포함)

학습 데이터가 다른 서버에만 있다면, 그 서버에서 아래 구조로 맞춘 뒤 같은 레포 + 같은 JSON으로 학습하면 된다.

```text
ml_datasets/ingredient_master_cls/
  train/
    ing_00001/
      a.jpg
    ing_00023/
      b.png
  val/
    ing_00001/
      ...
```

- 폴더 이름 = `export_yolo_label_assets_from_db.py`가 쓴 **model 키**와 동일해야 한다.
- 클래스당 이미지 수는 가능한 한 균등·충분히(수십 장 이상 권장, 부족한 클래스는 팀에서 보강).

### 9.3 원격 GPU에서 학습

```bash
# 서버에 레포 + ml_datasets + (필요 시) venv 복사 후
pip install -r requirements.txt
yolo classify train model=yolov8n-cls.pt data=./ml_datasets/ingredient_master_cls epochs=80 imgsz=224 batch=16 device=0 name=ing_master_v1
cp runs/classify/ing_master_v1/weights/best.pt app/models/ingredient/weights/raw_ingredient_best.pt
```

CUDA 인덱스(`device=0`)는 환경에 맞게 조정. 완성된 `best.pt`와 갱신된 `model_label_to_master.json`을 **FastAPI 배포 경로**에 같이 둔다.  
런타임: `RAW_INGREDIENT_MODEL_PATH` 로 가중치 경로를 덮어쓸 수 있다.

### 9.4 매핑 검증

```bash
python app/models/ingredient/tools/validate_raw_ingredient_mapping.py \
  --vocab app/models/ingredient/data/ingredient_normalized_vocab.json \
  --map app/models/ingredient/data/model_label_to_master.json
```

`normalizedName`이 어휘 `names`에 모두 들어가야 통과한다.

### 9.5 추천 원천 조합으로 `ml_datasets` 채우기

원천 다운로드 위치·라이선스: `data_sources/README.md`  

1. DB에서 `model_label_to_master.json` 생성(§9.1).  
2. GroceryStore / (선택) Fruits-360 / (선택) `team_uploads/train/ing_XXXXX/` 를 아래로 합친다.

```bash
python app/models/ingredient/tools/assemble_ingredient_master_cls_dataset.py \
  --master-json app/models/ingredient/data/model_label_to_master.json \
  --grocery-root data_sources/GroceryStoreDataset/dataset \
  --grocery-map app/models/ingredient/data/grocery_coarse_folder_to_normalized_name.json \
  --out ml_datasets/ingredient_master_cls \
  --mode copy
```

Fruits-360는 `app/models/ingredient/data/fruits360_folder_to_normalized_name.json` 의 `map`을 실제 폴더명에 맞게 채운 뒤:

```bash
python app/models/ingredient/tools/assemble_ingredient_master_cls_dataset.py \
  --master-json app/models/ingredient/data/model_label_to_master.json \
  --fruits360-root data_sources/Fruits-360/Training \
  --fruits360-map app/models/ingredient/data/fruits360_folder_to_normalized_name.json \
  --out ml_datasets/ingredient_master_cls \
  --mode copy
```

팀 보강만 있을 때는 `--team-root data_sources/team_uploads` 로 합치면 된다.

### 9.6 275 클래스 커버리지 확인

학습 전에 마스터의 모든 `ing_XXXXX`가 **train에 최소 1장** 있는지 확인한다.

```bash
python app/models/ingredient/tools/report_ingredient_master_cls_coverage.py \
  --master-json app/models/ingredient/data/model_label_to_master.json \
  --dataset-root ml_datasets/ingredient_master_cls \
  --min-train 1
```

부족 목록이 나오면 `data_sources/team_uploads/train/ing_XXXXX/` 에 이미지를 추가하고 `assemble` 을 다시 실행한다. CI에서 막으려면 `--fail-on-gap` 을 붙인다.

### 9.7 부족 클래스 CSV (수집·공유용)

```bash
python app/models/ingredient/tools/export_ingredient_cls_gap_checklist.py
```

기본 출력: `app/models/ingredient/data/ingredient_cls_gap_checklist.csv` (train 미달 행만). 전체 275행은 `--all-rows`.

### 9.8 “사진=재료”를 명시적으로만 맞추기

- **Grocery / Fruits-360**: `grocery_coarse_folder_to_normalized_name.json`, `fruits360_folder_to_normalized_name.json` 의 `map`(정확 일치)과 `prefixMap`(접두 일치, 긴 키 우선)에만 항목을 추가한다. 값은 항상 `ingredient_master`에 있는 `normalized_name` 뿐.
- **검증한 폴더를 한번에 넣기**: `ingest_verified_path_manifest.py` + CSV(`normalized_name`, `source_dir`). `data_sources/README.md` §4 참고.
- **한계**: “다진 당근”, “국간장” 같이 **가공·조리 형태 또는 병·포장**이 본질인 품목은 공개 전체·채소 사진으로 대체할 수 없다. 팀 촬영(또는 제품 사진)으로만 1:1을 맞출 수 있다.
