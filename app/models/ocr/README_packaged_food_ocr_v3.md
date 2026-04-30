# packagedFoodOcr v3

## 목적

PaddleOCR은 텍스트를 잘 읽어도 `1등급`, `세균수`, `체세포수`처럼 confidence가 높은 품질 문구를 먼저 반환할 수 있습니다.
v3는 OCR raw line은 보존하되, `displayName` 후보를 상품명 가능성이 높은 순서로 재정렬합니다.

## 적용

```bash
unzip packaged_food_ocr_v3.zip -d /tmp/packaged_food_ocr_v3

cp /tmp/packaged_food_ocr_v3/packagedFoodOcr.py \
  app/models/ocr/packagedFoodOcr.py
```

## 테스트

```bash
python app/models/ocr/packagedFoodOcr.py \
  --image app/models/ocr/우유.jpg \
  --topK 5 \
  --debug
```

## 기대

기존:
```json
"displayName": "1등급 1A등급 세균수 체세포수"
```

개선 목표:
```json
"displayName": "서울우유"
```
또는
```json
"displayName": "서울우유 우유"
```

## 주의

이 파일은 정규화/DB 매칭을 하지 않습니다.
`서울우유`를 `우유`로 매핑하는 것은 normalize 단계나 Spring Boot ingredient_master 매칭 단계에서 처리하는 것을 권장합니다.



## 테스트 실행 명령어
cd /Users/a0/Documents/git/project_final_backend_2

curl -X POST "http://localhost:8000/internal/v1/vision/recognize-ingredient-image" \
  -H "X-Internal-Service: spring-boot" \
  -H "X-Internal-Token: dev-secret" \
  -H "X-Request-Id: req_ocr_test_001" \
  -F "file=@app/models/ocr/우유.jpg" \
  -F "topK=3" \
  -F "detectMultiple=false" \
  -F "source=upload"