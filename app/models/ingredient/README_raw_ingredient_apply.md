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
