"""
이미지 인식 파이프라인 결과로부터 '이상 징후' 요약(휴리스틱).

별도 DL 모델이 없을 때도 동작하도록, 라우트·신뢰도·후보 유무로 신호를 만든다.
스키마는 Spring `AnomalyAnalysisDto` / 공개 API `anomalyAnalysis`와 맞춘다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_anomaly_analysis(
    route: str,
    route_confidence: float,
    route_needs_review: bool,
    candidates: List[Dict[str, Any]],
    pipeline_stage: str,
    needs_review: bool,
    dl_analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Returns camelCase keys for JSON: status, score, signals, modelVersion.
    - score: 0~1, 높을수록 파이프라인 결과를 신뢰할 수 있음.
    - status: OK | SUSPICIOUS | NEEDS_REVIEW
    """
    signals: List[str] = []
    top_conf: Optional[float] = None

    if candidates:
        try:
            top_conf = float(candidates[0].get("confidence") or 0.0)
        except (TypeError, ValueError):
            top_conf = 0.0
        if top_conf < 0.35:
            signals.append("LOW_TOP1_CONFIDENCE")

    if route_needs_review:
        signals.append("ROUTE_NEEDS_REVIEW")
    try:
        rc = float(route_confidence)
    except (TypeError, ValueError):
        rc = 0.0
    if rc < 0.5:
        signals.append("LOW_ROUTE_CONFIDENCE")
    if not candidates:
        signals.append("NO_CANDIDATES")
    if pipeline_stage in ("unsupported_route", "route_review_required"):
        signals.append("PIPELINE_UNCERTAIN")

    # 종합 점수 (간단한 가중 곱)
    score = 1.0
    if needs_review:
        score *= 0.55
    if not candidates:
        score *= 0.25
    else:
        t = top_conf if top_conf is not None else 0.4
        score *= max(0.15, min(1.0, t))
    score *= max(0.25, min(1.0, rc))

    score = round(max(0.0, min(1.0, score)), 4)

    dl_block: Optional[Dict[str, Any]] = None
    if dl_analysis:
        dl_block = dict(dl_analysis)
        dl_score = float(dl_analysis.get("combinedScore", 0.5))
        score = round(max(0.0, min(1.0, 0.5 * score + 0.5 * dl_score)), 4)
        for s in dl_analysis.get("signals") or []:
            if s not in signals:
                signals.append(s)

    if score >= 0.55 and not signals:
        status = "OK"
    elif score >= 0.3 or (not needs_review and bool(candidates)):
        status = "SUSPICIOUS"
    else:
        status = "NEEDS_REVIEW"

    mv = "heuristic_v1"
    if dl_analysis:
        mv = f"heuristic_v1+{dl_analysis.get('modelVersion', 'dl')}"

    out: Dict[str, Any] = {
        "status": status,
        "score": score,
        "signals": signals,
        "modelVersion": mv,
    }
    if dl_block is not None:
        # Spring camelCase: dlAnomaly
        out["dlAnomaly"] = dl_block
    return out
