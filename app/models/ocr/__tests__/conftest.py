"""
OCR 테스트 공통 설정.

목적
- 실제 PaddleOCR/YOLO 모델을 로딩하지 않고 문서 기준 테스트를 실행한다.
- 프로젝트 루트가 `app/` 패키지를 가진 정상 구조면 그대로 사용한다.
- 압축본처럼 `api/`, `models/`가 루트에 바로 있는 구조에서도 테스트를 미리 검토할 수 있게
  최소한의 import alias를 제공한다.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Dict

import pytest


def _find_project_root() -> Path:
    """tests/ocr/conftest.py 기준으로 프로젝트 루트를 추정한다."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "app").is_dir():
            return parent
        if (parent / "models").is_dir() and (parent / "api").is_dir():
            return parent
    return here.parents[2]


PROJECT_ROOT = _find_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 정상 프로젝트는 `app.models...` 구조다. 단, 현재 공유 압축본은 app 폴더 없이
# models/api만 들어 있을 수 있으므로 테스트 검토용 alias를 둔다.
if importlib.util.find_spec("app") is None and (PROJECT_ROOT / "models").is_dir():
    app_pkg = types.ModuleType("app")
    app_pkg.__path__ = [str(PROJECT_ROOT)]  # type: ignore[attr-defined]
    sys.modules.setdefault("app", app_pkg)

    for name in ("models", "api"):
        if (PROJECT_ROOT / name).is_dir():
            module = importlib.import_module(name)
            sys.modules.setdefault(f"app.{name}", module)
            setattr(app_pkg, name, module)

# visionInternalApi가 app.services.*를 import한다. 실제 프로젝트에 서비스가 있으면 그걸 쓰고,
# 압축본에 빠져 있으면 테스트용 더미 구현만 주입한다.
if importlib.util.find_spec("app.services") is None:
    services_pkg = types.ModuleType("app.services")
    services_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules.setdefault("app.services", services_pkg)

    vision_anomaly = types.ModuleType("app.services.vision_anomaly")

    def build_anomaly_analysis(**kwargs: Any) -> Dict[str, Any]:
        return {
            "mocked": True,
            "pipelineStage": kwargs.get("pipeline_stage"),
            "needsReview": kwargs.get("needs_review"),
        }

    vision_anomaly.build_anomaly_analysis = build_anomaly_analysis  # type: ignore[attr-defined]
    sys.modules.setdefault("app.services.vision_anomaly", vision_anomaly)

    vision_dl_anomaly = types.ModuleType("app.services.vision_dl_anomaly")

    def compute_dl_anomaly_analysis(image_path: Any) -> Dict[str, Any]:
        return {"mocked": True, "imagePath": str(image_path)}

    vision_dl_anomaly.compute_dl_anomaly_analysis = compute_dl_anomaly_analysis  # type: ignore[attr-defined]
    sys.modules.setdefault("app.services.vision_dl_anomaly", vision_dl_anomaly)


@pytest.fixture
def sample_jpeg_bytes() -> bytes:
    """FastAPI multipart 업로드에 사용할 작은 JPEG fixture."""
    try:
        from PIL import Image
        from io import BytesIO

        buffer = BytesIO()
        image = Image.new("RGB", (12, 12), color=(255, 255, 255))
        image.save(buffer, format="JPEG")
        return buffer.getvalue()
    except Exception:
        # Pillow가 깨진 환경에서도 API 입력 검증 테스트는 가능하도록 최소 JPEG header를 제공한다.
        return b"\xff\xd8\xff\xe0" + b"0" * 32 + b"\xff\xd9"


@pytest.fixture
def internal_headers(monkeypatch: pytest.MonkeyPatch) -> Dict[str, str]:
    monkeypatch.setenv("INTERNAL_API_TOKEN", "dev-secret")
    monkeypatch.delenv("INTERNAL_API_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("INTERNAL_API_STRICT", raising=False)
    return {
        "X-Internal-Service": "spring-boot",
        "X-Internal-Token": "dev-secret",
        "X-Request-Id": "req_ocr_test_001",
    }
