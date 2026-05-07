from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.ocr import packagedFoodOcr as ocr_module
from app.models.ocr.packagedFoodOcr import (
    OcrLine,
    PackagedFoodOcr,
    clean_ocr_text,
    is_noise_text,
    safe_float,
    score_product_title_line,
)


@pytest.mark.unit
def test_ut_ocr_001_clean_score_and_dedupe_lines() -> None:
    """UT-OCR-001: OCR 텍스트/점수/라인 정리."""
    assert clean_ocr_text("  서울   우유  ") == "서울 우유"
    assert safe_float("0.91") == pytest.approx(0.91)
    assert safe_float("abc", default=0.0) == 0.0
    assert safe_float(None, default=0.25) == 0.25

    lines = [
        OcrLine(text="서울우유", confidence=0.91),
        OcrLine(text="서울우유", confidence=0.88),
        OcrLine(text="1등급", confidence=0.95),
    ]

    deduped = PackagedFoodOcr._dedupe_lines(lines)

    assert [line.text for line in deduped] == ["서울우유", "1등급"]


@pytest.mark.unit
def test_ut_ocr_002_parse_paddleocr_v3_and_legacy_result_shapes() -> None:
    """UT-OCR-002: PaddleOCR 3.x dict 형식과 legacy list/tuple 형식 파싱."""
    parser = PackagedFoodOcr.__new__(PackagedFoodOcr)

    paddle3_result = {
        "res": {
            "rec_texts": ["  서울   우유  ", "", "1등급"],
            "rec_scores": ["0.93", "0.10", "bad-score"],
            "rec_boxes": [[10, 10, 120, 50], [0, 0, 1, 1], [10, 80, 100, 120]],
        }
    }
    parsed_v3 = parser._parse_ocr_result(paddle3_result)

    assert len(parsed_v3) == 2
    assert parsed_v3[0].text == "서울 우유"
    assert parsed_v3[0].confidence == pytest.approx(0.93)
    assert parsed_v3[0].box == [10, 10, 120, 50]
    assert parsed_v3[1].text == "1등급"
    assert parsed_v3[1].confidence == 0.0

    legacy_box = [[10, 10], [120, 10], [120, 50], [10, 50]]
    legacy_result = [[legacy_box, ("서울우유", 0.94)]]
    parsed_legacy = parser._parse_ocr_result(legacy_result)

    assert len(parsed_legacy) == 1
    assert parsed_legacy[0].text == "서울우유"
    assert parsed_legacy[0].confidence == pytest.approx(0.94)
    assert parsed_legacy[0].box == legacy_box


@pytest.mark.unit
def test_ut_ocr_003_product_title_line_scores_higher_than_package_noise() -> None:
    """UT-OCR-003: 상품명 후보와 노이즈 문구 구분."""
    product_score = score_product_title_line(
        text="서울우유",
        confidence=0.80,
        box=[20, 20, 210, 80],
        image_size=(300, 300),
    )
    weak_product_score = score_product_title_line(
        text="우유",
        confidence=0.80,
        box=[20, 20, 120, 70],
        image_size=(300, 300),
    )
    noise_score = score_product_title_line(
        text="1등급 세균수 200ml 소비기한",
        confidence=0.95,
        box=[20, 230, 260, 280],
        image_size=(300, 300),
    )

    assert product_score > weak_product_score
    assert product_score > noise_score
    assert is_noise_text("1등급 세균수 200ml 소비기한") is True
    assert is_noise_text("서울우유") is False


@pytest.mark.unit
def test_ut_ocr_004_build_representative_candidates_without_noise_or_duplicates() -> None:
    """UT-OCR-004: 대표 상품명 후보 생성."""
    ocr = PackagedFoodOcr.__new__(PackagedFoodOcr)
    ocr.min_text_confidence = 0.30
    ocr.max_merge_lines = 3

    raw_lines = [
        OcrLine(text="1등급 세균수", confidence=0.99, box=[20, 230, 240, 270]),
        OcrLine(text="서울우유", confidence=0.87, box=[20, 25, 220, 85]),
        OcrLine(text="우유", confidence=0.92, box=[20, 90, 120, 130]),
        OcrLine(text="나100%", confidence=0.77, box=[20, 135, 140, 170]),
    ]
    scored_lines = ocr._score_lines(raw_lines, image_size=(300, 300))

    candidates = ocr._build_candidates(scored_lines, top_k=3)

    assert 1 <= len(candidates) <= 3
    assert candidates[0].displayName == "서울우유"
    assert "1등급" not in candidates[0].displayName
    assert candidates[0].normalizedName == candidates[0].displayName
    assert candidates[0].ocrText
    assert candidates[0].ocrLines
    assert candidates[0].extractionReason in {
        "merged_product_title_lines",
        "single_product_title_line",
    }


@pytest.mark.unit
def test_ut_ocr_005_failures_env_and_candidate_contract_are_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UT-OCR-005: 예외·환경설정·후보 변환 안전성."""
    ocr = PackagedFoodOcr.__new__(PackagedFoodOcr)
    ocr.debug = False
    ocr.min_text_confidence = 0.30
    ocr.max_merge_lines = 3
    ocr._parse_ocr_result = lambda raw_result: []  # type: ignore[method-assign]
    ocr._run_ocr = lambda image_path: []  # type: ignore[method-assign]

    with pytest.raises(FileNotFoundError):
        ocr.recognize(tmp_path / "missing.jpg", top_k=3)

    from PIL import Image

    image_path = tmp_path / "empty.jpg"
    Image.new("RGB", (10, 10), color=(255, 255, 255)).save(image_path)
    assert ocr.recognize(image_path, top_k=3) == []

    monkeypatch.setattr(ocr_module, "_ocr_instance", None)
    monkeypatch.setenv("PACKAGED_FOOD_OCR_LANG", "korean")
    monkeypatch.setenv("PACKAGED_FOOD_OCR_MIN_CONFIDENCE", "0.55")
    monkeypatch.setenv("PACKAGED_FOOD_OCR_MAX_MERGE_LINES", "2")
    monkeypatch.setenv("PACKAGED_FOOD_OCR_DEBUG", "true")

    with patch.object(PackagedFoodOcr, "_load_ocr", return_value=object()):
        configured = ocr_module.get_packaged_food_ocr()

    assert configured.lang == "korean"
    assert configured.min_text_confidence == pytest.approx(0.55)
    assert configured.max_merge_lines == 2
    assert configured.debug is True

    from app.api.internal.visionInternalApi import normalize_candidates

    normalized = normalize_candidates(
        ["서울우유", {"display_name": "두부", "score": "0.84", "category": "가공식품"}],
        default_category=None,
    )

    assert normalized == [
        {
            "displayName": "서울우유",
            "normalizedName": "서울우유",
            "categorySuggestion": None,
            "confidence": 0.0,
            "bbox": None,
        },
        {
            "displayName": "두부",
            "normalizedName": "두부",
            "categorySuggestion": "가공식품",
            "confidence": 0.84,
            "bbox": None,
        },
    ]
