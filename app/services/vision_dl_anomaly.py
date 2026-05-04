"""
이미지 픽셀 기반 이상 탐지 (경량, NumPy/PIL).

- 라플라시안 분산 → 초점/블러 의심
- 평균 휘도 → 과다/과소 노출 의심
- 선택: 환경변수 VISION_ANOMALY_TORCH_SCRIPT 에 TorchScript 경로가 있으면 추가 특성

별도 학습 데이터 없이 동작하는 **실제 이미지→수치** 파이프라인이다.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


def _to_gray(rgb: np.ndarray) -> np.ndarray:
    return (
        0.299 * rgb[:, :, 0]
        + 0.587 * rgb[:, :, 1]
        + 0.114 * rgb[:, :, 2]
    ).astype(np.float64)


def _laplacian_variance(gray: np.ndarray) -> float:
    """간단 4-이웃 라플라시안 분산."""
    if gray.size < 9:
        return 0.0
    lap = (
        -4.0 * gray
        + np.roll(gray, 1, axis=0)
        + np.roll(gray, -1, axis=0)
        + np.roll(gray, 1, axis=1)
        + np.roll(gray, -1, axis=1)
    )
    # 경계 아티팩트 제거
    lap = lap[1:-1, 1:-1]
    return float(np.var(lap))


def compute_dl_anomaly_analysis(image_path: Path) -> Dict[str, Any]:
    """
    Returns keys aligned with Spring AnomalyAnalysisDto.dlAnomaly / camelCase:
      blurScore, exposureScore, combinedScore, signals, modelVersion
    """
    signals: List[str] = []
    p = Path(image_path)
    if not p.exists():
        return {
            "blurScore": 0.0,
            "exposureScore": 0.5,
            "combinedScore": 0.3,
            "signals": ["FILE_MISSING"],
            "modelVersion": "laplacian_exposure_v1",
        }

    try:
        from PIL import Image

        img = Image.open(p).convert("RGB")
        rgb = np.asarray(img, dtype=np.float64)
    except Exception:
        return {
            "blurScore": 0.0,
            "exposureScore": 0.5,
            "combinedScore": 0.25,
            "signals": ["IMAGE_DECODE_FAILED"],
            "modelVersion": "laplacian_exposure_v1",
        }

    gray = _to_gray(rgb) / 255.0
    lap_var = _laplacian_variance(gray)
    mean_lum = float(np.mean(gray))

    # 경험적 임계: 분산 매우 낮으면 블러 의심
    blur_norm = min(1.0, lap_var / 0.02)  # 0.02 넘으면 선명 쪽
    blur_score = float(np.clip(blur_norm, 0.0, 1.0))

    if lap_var < 30.0:
        signals.append("BLUR_SUSPECT")

    # 노출: 0.5 근처가 이상적
    exposure_score = 1.0 - min(abs(mean_lum - 0.5) * 2.0, 1.0)
    if mean_lum < 0.08:
        signals.append("UNDEREXPOSED")
    if mean_lum > 0.92:
        signals.append("OVEREXPOSED")

    combined = 0.55 * blur_score + 0.45 * exposure_score

    extra = _optional_torch_script_features(p)
    if extra:
        combined = 0.7 * combined + 0.3 * float(extra.get("torchScore", combined))
        signals.extend(extra.get("signals", []))

    ver = "laplacian_exposure_v1" + ("+torch" if extra else "")
    return {
        "blurScore": round(blur_score, 4),
        "exposureScore": round(exposure_score, 4),
        "laplacianVariance": round(lap_var, 4),
        "meanLuminance": round(mean_lum, 4),
        "combinedScore": round(float(np.clip(combined, 0.0, 1.0)), 4),
        "signals": signals,
        "modelVersion": ver,
    }


def _optional_torch_script_features(image_path: Path) -> Dict[str, Any] | None:
    path = os.environ.get("VISION_ANOMALY_TORCH_SCRIPT", "").strip()
    if not path or not Path(path).exists():
        return None
    try:
        import torch

        model = torch.jit.load(path, map_location="cpu")
        from PIL import Image

        img = Image.open(image_path).convert("RGB").resize((224, 224))
        x = np.asarray(img, dtype=np.float32) / 255.0
        x = np.transpose(x, (2, 0, 1))
        t = torch.from_numpy(x).unsqueeze(0)
        with torch.no_grad():
            out = model(t)
        # 단일 스칼라 또는 벡터 첫 값을 점수로
        if hasattr(out, "numpy"):
            arr = out.numpy().flatten()
        else:
            arr = np.asarray(out).flatten()
        score = float(np.clip(arr[0] if arr.size > 0 else 0.5, 0.0, 1.0))
        return {"torchScore": score, "signals": ["TORCH_SCRIPT_USED"]}
    except Exception:
        return {"torchScore": 0.5, "signals": ["TORCH_SCRIPT_ERROR"]}
