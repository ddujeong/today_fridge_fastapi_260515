from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.internal import visionInternalApi as vision_api


class FakeRouteClassifier:
    def __init__(self, result: Dict[str, Any]) -> None:
        self.result = result

    def classify_image(self, image_path: Path) -> Dict[str, Any]:
        assert Path(image_path).exists()
        return dict(self.result)


def _route_result(
    *,
    route: str,
    confidence: float,
    needs_review: bool = False,
) -> Dict[str, Any]:
    return {
        "route": route,
        "confidence": confidence,
        "needs_user_confirmation": needs_review,
        "reason": f"{route} mocked",
        "probabilities": {route: confidence},
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    app = FastAPI()
    app.include_router(vision_api.router)

    # 이미지 이상 탐지 서비스는 OCR 통합 흐름의 본질이 아니므로 고정값으로 둔다.
    monkeypatch.setattr(vision_api, "compute_dl_anomaly_analysis", lambda path: {"mocked": True})
    monkeypatch.setattr(
        vision_api,
        "build_anomaly_analysis",
        lambda **kwargs: {
            "mocked": True,
            "pipelineStage": kwargs.get("pipeline_stage"),
            "needsReview": kwargs.get("needs_review"),
        },
    )
    return TestClient(app)


def _post_image(
    client: TestClient,
    sample_jpeg_bytes: bytes,
    headers: Dict[str, str],
    *,
    top_k: int = 3,
    content_type: str = "image/jpeg",
    filename: str = "milk.jpg",
) -> Any:
    return client.post(
        "/internal/v1/vision/recognize-ingredient-image",
        headers=headers,
        data={"topK": str(top_k), "detectMultiple": "false", "source": "upload"},
        files={"file": (filename, sample_jpeg_bytes, content_type)},
    )


@pytest.mark.integration
def test_it_ocr_001_internal_api_auth_and_image_upload_returns_envelope(
    client: TestClient,
    sample_jpeg_bytes: bytes,
    internal_headers: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IT-OCR-001: 내부 API 인증과 이미지 업로드."""
    monkeypatch.setattr(
        vision_api,
        "get_route_classifier",
        lambda: FakeRouteClassifier(_route_result(route="raw_ingredient", confidence=0.91)),
    )
    monkeypatch.setattr(
        vision_api,
        "recognize_raw_ingredient_by_classifier",
        lambda image_path, top_k: [
            {
                "displayName": "양파",
                "normalizedName": "양파",
                "categorySuggestion": "채소",
                "confidence": 0.91,
                "bbox": None,
            }
        ],
    )

    response = _post_image(client, sample_jpeg_bytes, internal_headers)
    body = response.json()

    assert response.status_code == 200
    assert body["success"] is True
    assert body["code"] == "OK"
    assert body["message"] == "recognized"
    assert body["requestId"] == "req_ocr_test_001"
    assert body["data"]["pipeline"]["source"] == "upload"
    assert body["data"]["recognizedCandidates"][0]["displayName"] == "양파"


@pytest.mark.integration
def test_it_ocr_002_packaged_food_route_returns_ocr_candidates(
    client: TestClient,
    sample_jpeg_bytes: bytes,
    internal_headers: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IT-OCR-002: 포장식품 라우팅 후 OCR 후보 반환."""
    monkeypatch.setattr(
        vision_api,
        "get_route_classifier",
        lambda: FakeRouteClassifier(_route_result(route="packaged_food", confidence=0.97)),
    )
    monkeypatch.setattr(
        vision_api,
        "recognize_packaged_food_by_ocr",
        lambda image_path, top_k: [
            {
                "displayName": "서울우유",
                "normalizedName": "서울우유",
                "categorySuggestion": None,
                "confidence": 0.88,
                "bbox": None,
            }
        ],
    )
    monkeypatch.setattr(vision_api, "recognize_raw_ingredient_by_classifier", lambda image_path, top_k: [])

    response = _post_image(client, sample_jpeg_bytes, internal_headers, top_k=3)
    data = response.json()["data"]

    assert data["pipeline"]["stage"] == "packaged_food_ocr"
    assert data["route"]["type"] == "packaged_food"
    assert data["needsReview"] is False
    assert data["recognizedCandidates"] == [
        {
            "displayName": "서울우유",
            "normalizedName": "서울우유",
            "categorySuggestion": None,
            "confidence": 0.88,
            "bbox": None,
        }
    ]


@pytest.mark.integration
def test_it_ocr_003_empty_ocr_candidates_need_review_or_raw_override(
    client: TestClient,
    sample_jpeg_bytes: bytes,
    internal_headers: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IT-OCR-003: OCR 후보 없음 또는 낮은 신뢰도 처리."""
    monkeypatch.setattr(
        vision_api,
        "get_route_classifier",
        lambda: FakeRouteClassifier(_route_result(route="packaged_food", confidence=0.95)),
    )
    monkeypatch.setattr(vision_api, "recognize_packaged_food_by_ocr", lambda image_path, top_k: [])
    monkeypatch.setattr(vision_api, "recognize_raw_ingredient_by_classifier", lambda image_path, top_k: [])

    empty_response = _post_image(client, sample_jpeg_bytes, internal_headers)
    empty_data = empty_response.json()["data"]

    assert empty_data["pipeline"]["stage"] == "packaged_food_ocr"
    assert empty_data["recognizedCandidates"] == []
    assert empty_data["needsReview"] is True

    monkeypatch.setattr(
        vision_api,
        "get_route_classifier",
        lambda: FakeRouteClassifier(_route_result(route="packaged_food", confidence=0.50)),
    )
    monkeypatch.setattr(
        vision_api,
        "recognize_raw_ingredient_by_classifier",
        lambda image_path, top_k: [
            {
                "displayName": "양파",
                "normalizedName": "양파",
                "categorySuggestion": "채소",
                "confidence": 0.86,
                "bbox": None,
            }
        ],
    )

    override_response = _post_image(client, sample_jpeg_bytes, internal_headers)
    override_data = override_response.json()["data"]

    assert override_data["pipeline"]["stage"] == "raw_ingredient_classifier_override"
    assert override_data["route"]["type"] == "raw_ingredient"
    assert override_data["needsReview"] is False
    assert override_data["recognizedCandidates"][0]["displayName"] == "양파"


@pytest.mark.integration
def test_it_ocr_004_invalid_requests_return_clear_errors(
    client: TestClient,
    sample_jpeg_bytes: bytes,
    internal_headers: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IT-OCR-004: 잘못된 요청 검증."""
    monkeypatch.setattr(
        vision_api,
        "get_route_classifier",
        lambda: FakeRouteClassifier(_route_result(route="packaged_food", confidence=0.97)),
    )

    invalid_token_headers = dict(internal_headers)
    invalid_token_headers["X-Internal-Token"] = "wrong-token"
    invalid_token = _post_image(client, sample_jpeg_bytes, invalid_token_headers)
    invalid_token_body = invalid_token.json()["detail"]

    assert invalid_token.status_code == 403
    assert invalid_token_body["success"] is False
    assert invalid_token_body["code"] == "INTERNAL_VALIDATION_ERROR"
    assert invalid_token_body["errors"][0]["field"] == "X-Internal-Token"

    wrong_file = _post_image(
        client,
        b"not-image",
        internal_headers,
        content_type="text/plain",
        filename="not-image.txt",
    )
    wrong_file_body = wrong_file.json()

    assert wrong_file.status_code == 200
    assert wrong_file_body["success"] is False
    assert wrong_file_body["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert wrong_file_body["errors"][0]["field"] == "file"

    invalid_top_k = _post_image(client, sample_jpeg_bytes, internal_headers, top_k=0)
    invalid_top_k_body = invalid_top_k.json()

    assert invalid_top_k.status_code == 200
    assert invalid_top_k_body["success"] is False
    assert invalid_top_k_body["code"] == "INTERNAL_VALIDATION_ERROR"
    assert invalid_top_k_body["errors"][0]["field"] == "topK"


@pytest.mark.integration
def test_it_ocr_005_model_error_returns_model_unavailable_and_removes_temp_file(
    client: TestClient,
    sample_jpeg_bytes: bytes,
    internal_headers: Dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """IT-OCR-005: OCR/모델 오류와 임시파일 정리."""
    temp_image_path = tmp_path / "fixed_uploaded_image.jpg"

    class FixedNamedTemporaryFile:
        def __init__(self, delete: bool = False, suffix: str = "") -> None:
            self.name = str(temp_image_path.with_suffix(suffix or ".jpg"))
            self._fp = None

        def __enter__(self) -> "FixedNamedTemporaryFile":
            self._fp = open(self.name, "wb")
            return self

        def write(self, content: bytes) -> int:
            assert self._fp is not None
            return self._fp.write(content)

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            if self._fp is not None:
                self._fp.close()

    monkeypatch.setattr(vision_api.tempfile, "NamedTemporaryFile", FixedNamedTemporaryFile)
    monkeypatch.setattr(
        vision_api,
        "get_route_classifier",
        lambda: FakeRouteClassifier(_route_result(route="packaged_food", confidence=0.97)),
    )

    def raise_ocr_error(image_path: Path, top_k: int) -> List[Dict[str, Any]]:
        assert Path(image_path).exists()
        raise RuntimeError("OCR engine unavailable")

    monkeypatch.setattr(vision_api, "recognize_packaged_food_by_ocr", raise_ocr_error)

    response = _post_image(client, sample_jpeg_bytes, internal_headers)
    body = response.json()

    assert response.status_code == 200
    assert body["success"] is False
    assert body["code"] == "MODEL_UNAVAILABLE"
    assert "OCR engine unavailable" in body["message"]
    assert not temp_image_path.exists()
