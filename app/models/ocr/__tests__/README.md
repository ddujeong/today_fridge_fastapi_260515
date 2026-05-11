# 오늘냉장고 OCR 테스트 코드 묶음

이 zip은 `오늘냉장고_OCR_단위_통합테스트_문서_v1.1.xlsm`의 10개 테스트 케이스에 맞춘 `pytest` 테스트 코드입니다.

## 포함 파일

```text
tests/ocr/conftest.py
tests/ocr/test_packaged_food_ocr_unit.py
tests/ocr/test_vision_ocr_api_integration.py
pytest.ini
```

## 대응 문서 항목

| 문서 ID | 테스트 함수 |
|---|---|
| UT-OCR-001 | `test_ut_ocr_001_clean_score_and_dedupe_lines` |
| UT-OCR-002 | `test_ut_ocr_002_parse_paddleocr_v3_and_legacy_result_shapes` |
| UT-OCR-003 | `test_ut_ocr_003_product_title_line_scores_higher_than_package_noise` |
| UT-OCR-004 | `test_ut_ocr_004_build_representative_candidates_without_noise_or_duplicates` |
| UT-OCR-005 | `test_ut_ocr_005_failures_env_and_candidate_contract_are_explicit` |
| IT-OCR-001 | `test_it_ocr_001_internal_api_auth_and_image_upload_returns_envelope` |
| IT-OCR-002 | `test_it_ocr_002_packaged_food_route_returns_ocr_candidates` |
| IT-OCR-003 | `test_it_ocr_003_empty_ocr_candidates_need_review_or_raw_override` |
| IT-OCR-004 | `test_it_ocr_004_invalid_requests_return_clear_errors` |
| IT-OCR-005 | `test_it_ocr_005_model_error_returns_model_unavailable_and_removes_temp_file` |

## 적용 위치

프로젝트 루트 기준으로 압축을 풀면 됩니다.

예시:

```bash
cd /Users/a0/Documents/git/project_final_backend_2
unzip today_fridge_ocr_tests_v1.0.zip
```

정상 프로젝트 구조는 다음 중 하나를 지원합니다.

```text
project_final_backend_2/app/models/ocr/packagedFoodOcr.py
project_final_backend_2/app/api/internal/visionInternalApi.py
```

또는 현재 공유 압축본처럼 `app/` 없이 `models/`, `api/`가 루트에 있는 구조도 `conftest.py`가 테스트 검토용 alias를 제공합니다.

## 실행 명령어

전체 실행:

```bash
pytest tests/ocr -q
```

단위테스트만 실행:

```bash
pytest tests/ocr/test_packaged_food_ocr_unit.py -q
```

통합테스트만 실행:

```bash
pytest tests/ocr/test_vision_ocr_api_integration.py -q
```

마커 기준 실행:

```bash
pytest tests/ocr -m unit -q
pytest tests/ocr -m integration -q
```

## 테스트 설계 원칙

- PaddleOCR, YOLO 모델은 실제 로딩하지 않습니다.
- OCR 단위테스트는 파싱/스코어링/후보 생성/예외/환경설정/응답계약을 Mock 중심으로 검증합니다.
- 통합테스트는 FastAPI `TestClient`로 내부 API endpoint를 호출하되, route classifier와 OCR/raw classifier는 Mock 처리합니다.
- 실제 이미지 OCR 정확도 검증은 별도의 smoke/e2e 테스트로 분리하는 것을 권장합니다.

## 필요 패키지

프로젝트 기존 의존성 외에 보통 아래가 필요합니다.

```bash
pip install pytest fastapi httpx pillow python-multipart
```

FastAPI `UploadFile`, `Form`, multipart 테스트를 사용하므로 `python-multipart`가 없으면 route import 단계에서 실패할 수 있습니다.
