"""
vision_internal_api.py

오늘냉장고 FastAPI 내부 이미지 인식 오케스트레이션 API.

흐름:
1. Spring Boot가 /internal/v1/vision/recognize-ingredient-image 호출
2. FastAPI가 업로드 이미지를 임시 저장
3. ingredient_route_cls_classifier(YOLO)로 1차 라우팅
4. packaged_food이면 OCR 모듈 호출
5. raw_ingredient이면 식재료 세부 classifier 모듈 호출
6. 모델이 ing_* 마스터 클래스만 학습된 경우(예: ing_master_124_cls): softmax 상위 K + model_label_to_master_train_non_packaged.json 으로 후보 생성
7. 문서 계약의 recognizedCandidates 형태로 응답

현재 전제:
- route classifier는 이미 구현되어 있음.
- packaged_food_ocr.py, raw_ingredient_classifier.py는 별도 파일로 구현 예정.
- 그래서 이 파일은 두 후속 모듈을 "느슨한 adapter"로 호출한다.
  후속 모듈이 아직 없으면 해당 route에서 MODEL_UNAVAILABLE 응답을 반환한다.

권장 파일 위치:
    app/internal/vision_internal_api.py

main.py 연결:
    from app.internal.vision_internal_api import router as vision_internal_router
    app.include_router(vision_internal_router)
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from app.models.img2class.ingredientRouteClassifier import IngredientRouteClassifier
from app.models.ocr.packagedFoodOcr import recognize_packaged_food_image
from app.services.embedding_service import generate_embedding
from app.services.vision_anomaly import build_anomaly_analysis
from app.services.vision_dl_anomaly import compute_dl_anomaly_analysis

router = APIRouter(prefix="/internal/v1", tags=["internal-vision"])

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

DEFAULT_ROUTE_MODEL_PATH = "app/models/img2class/best.pt"
MAX_RECOGNITION_CANDIDATES = 3
PACKAGED_ROUTE_FALLBACK_MAX_CONF = 0.90
RAW_OVERRIDE_MIN_CONFIDENCE = 0.45
EMBEDDING_RERANK_ENABLED_DEFAULT = True

# YOLO train 폴더명 ing_00042 형태 → DB 마스터 표시명 매핑 (비포장 124클 등)
_MASTER_LABEL_JSON_DEFAULT = (
    Path(__file__).resolve().parents[2]
    / "models"
    / "ingredient"
    / "data"
    / "model_label_to_master_train_non_packaged.json"
)
_TRAIN_CLASS_REF_CSV_DEFAULT = (
    Path(__file__).resolve().parents[2]
    / "models"
    / "ingredient"
    / "data"
    / "train_class_reference_new.csv"
)
_ING_CLASS_KEY = re.compile(r"^ing_\d+$", re.IGNORECASE)

_route_classifier: Optional[IngredientRouteClassifier] = None
_route_classifier_load_error: Optional[str] = None
_master_labels_by_key: Optional[Dict[str, Any]] = None
_train_class_ref_by_folder: Optional[Dict[str, Dict[str, str]]] = None


def common_success(
    *,
    data: Dict[str, Any],
    request_id: str,
    message: str = "internal request succeeded",
    code: str = "OK",
) -> Dict[str, Any]:
    return {
        "success": True,
        "code": code,
        "message": message,
        "data": data,
        "requestId": request_id,
    }


def common_error(
    *,
    code: str,
    message: str,
    request_id: str,
    errors: Optional[List[Dict[str, Any]]] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    response = {
        "success": False,
        "code": code,
        "message": message,
        "data": data or {},
        "requestId": request_id,
    }
    if errors is not None:
        response["errors"] = errors
    return response


def make_request_id(x_request_id: Optional[str]) -> str:
    if x_request_id and x_request_id.strip():
        return x_request_id.strip()
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"req_{now}_{uuid.uuid4().hex[:8]}"


_ALLOWED_INTERNAL_SERVICES = frozenset({"spring-boot", "spring-backend"})


def verify_internal_call(
    *,
    x_internal_service: Optional[str],
    x_internal_token: Optional[str],
    request_id: str,
) -> None:
    """
    내부 API 보호용 최소 검증.

    로컬 개발 중 토큰 없이 테스트하려면:
        export INTERNAL_API_ALLOW_NO_TOKEN=true

    팀 공유/배포 환경에서는 반드시:
        export INTERNAL_API_TOKEN="..."
        (운영에서는 INTERNAL_API_STRICT=true 권장 — 토큰 미설정 시 기본값 사용 안 함)
    """
    strict = os.getenv("INTERNAL_API_STRICT", "false").lower() == "true"
    expected_token = os.getenv("INTERNAL_API_TOKEN")

    if not expected_token:
        allow_no_token = os.getenv("INTERNAL_API_ALLOW_NO_TOKEN", "false").lower() == "true"
        if allow_no_token:
            return
        if strict:
            raise HTTPException(
                status_code=500,
                detail=common_error(
                    code="MODEL_UNAVAILABLE",
                    message="INTERNAL_API_TOKEN is not configured",
                    request_id=request_id,
                ),
            )
        # Spring application.yml 기본 app.fastapi.service-key 와 맞춤 (로컬 bootRun)
        expected_token = "change-me"

    if x_internal_service not in _ALLOWED_INTERNAL_SERVICES:
        raise HTTPException(
            status_code=403,
            detail=common_error(
                code="INTERNAL_VALIDATION_ERROR",
                message="invalid X-Internal-Service",
                request_id=request_id,
                errors=[
                    {
                        "field": "X-Internal-Service",
                        "reason": "must be spring-boot or spring-backend",
                    }
                ],
            ),
        )

    if x_internal_token != expected_token:
        raise HTTPException(
            status_code=403,
            detail=common_error(
                code="INTERNAL_VALIDATION_ERROR",
                message="invalid X-Internal-Token",
                request_id=request_id,
                errors=[
                    {
                        "field": "X-Internal-Token",
                        "reason": "does not match server token",
                    }
                ],
            ),
        )


def get_route_classifier() -> IngredientRouteClassifier:
    global _route_classifier, _route_classifier_load_error

    if _route_classifier is not None:
        return _route_classifier

    model_path = os.getenv("INGREDIENT_ROUTE_MODEL_PATH", DEFAULT_ROUTE_MODEL_PATH)
    threshold = float(os.getenv("INGREDIENT_ROUTE_CONFIDENCE_THRESHOLD", "0.60"))
    device = os.getenv("INGREDIENT_ROUTE_DEVICE") or None
    imgsz = int(os.getenv("INGREDIENT_ROUTE_IMGSZ", "224"))

    try:
        _route_classifier = IngredientRouteClassifier(
            model_path=model_path,
            confidence_threshold=threshold,
            device=device,
            imgsz=imgsz,
        )
        _route_classifier_load_error = None
        return _route_classifier
    except Exception as exc:
        _route_classifier_load_error = str(exc)
        raise


def recognize_packaged_food_by_ocr(image_path: Path, top_k: int) -> List[Dict[str, Any]]:
    """
    packaged_food 후속 처리 adapter.

    아래 함수가 구현되어 있다고 가정한다.

        app.models.ocr.packaged_food_ocr.recognize_packaged_food_image(
            image_path: str | Path,
            top_k: int = 5,
        ) -> list[dict] | dict | str

    반환 dict 권장 형식:
        {
          "displayName": "서울우유",
          "normalizedName": "우유",
          "categorySuggestion": "유제품",
          "confidence": 0.91
        }
    """
    try:
        from app.models.ocr.packagedFoodOcr import recognize_packaged_food_image
    except ImportError as exc:
        raise RuntimeError(
            "packaged_food_ocr.py 또는 recognize_packaged_food_image 함수가 없습니다."
        ) from exc

    raw_result = recognize_packaged_food_image(image_path=image_path, top_k=top_k)
    return normalize_candidates(raw_result, default_category=None)


def recognize_raw_ingredient_by_classifier(image_path: Path, top_k: int) -> List[Dict[str, Any]]:
    """
    raw_ingredient 후속 처리 adapter.

    아래 함수가 구현되어 있다고 가정한다.

        app.models.ingredient.rawIngredientClassifier.recognize_raw_ingredient_image(
            image_path: str | Path,
            top_k: int = 5,
        ) -> list[dict] | dict | str

    반환 dict 권장 형식:
        {
          "displayName": "양파",
          "normalizedName": "양파",
          "categorySuggestion": "채소",
          "confidence": 0.97
        }
    """
    try:
        from app.models.ingredient.rawIngredientClassifier import recognize_raw_ingredient_image
    except ImportError as exc:
        raise RuntimeError(
            "raw_ingredient_classifier.py 또는 recognize_raw_ingredient_image 함수가 없습니다."
        ) from exc

    raw_result = recognize_raw_ingredient_image(image_path=image_path, top_k=top_k)
    return normalize_candidates(raw_result, default_category=None)


def _load_master_train_label_map() -> Dict[str, Any]:
    """model_label_to_master_train_non_packaged.json 의 labels 맵 (키: ing_00007)."""
    global _master_labels_by_key
    if _master_labels_by_key is not None:
        return _master_labels_by_key
    path = Path(
        os.getenv("INGREDIENT_MASTER_TRAIN_LABEL_JSON", str(_MASTER_LABEL_JSON_DEFAULT))
    )
    if not path.is_file():
        _master_labels_by_key = {}
        return _master_labels_by_key
    with open(path, encoding="utf-8") as f:
        root = json.load(f)
    labels = root.get("labels")
    _master_labels_by_key = labels if isinstance(labels, dict) else {}
    return _master_labels_by_key


def _canonical_ing_folder_key(label: str) -> str:
    """ing_7 / ing_00007 / ING_00007 → ing_00007 (학습 폴더·CSV·JSON 키 통일)."""
    s = str(label).strip()
    m = re.match(r"^(?i)ing_(\d+)$", s)
    if not m:
        return s
    return f"ing_{int(m.group(1)):05d}"


def _load_train_class_reference_map() -> Dict[str, Dict[str, str]]:
    """train_class_reference_new.csv — JSON에 없는 ing_* 도 표시명 조회."""
    global _train_class_ref_by_folder
    if _train_class_ref_by_folder is not None:
        return _train_class_ref_by_folder
    import csv

    path = Path(os.getenv("TRAIN_CLASS_REFERENCE_CSV", str(_TRAIN_CLASS_REF_CSV_DEFAULT)))
    out: Dict[str, Dict[str, str]] = {}
    if not path.is_file():
        _train_class_ref_by_folder = out
        return out
    # utf-8-sig: Excel/메모장 저장 시 BOM 으로 첫 헤더가 \ufeffclass_folder 가 되어 class_folder 조회가 전부 실패하는 것 방지
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = (row.get("class_folder") or "").strip()
            if not raw:
                # BOM 깨진 헤더 대비
                for k, v in row.items():
                    if k and k.replace("\ufeff", "").strip().lower() == "class_folder" and v:
                        raw = str(v).strip()
                        break
            if not raw:
                continue
            canon = _canonical_ing_folder_key(raw)
            clean_row = {
                (k.replace("\ufeff", "").strip() if isinstance(k, str) else k): (
                    (v or "").strip() if isinstance(v, str) else v
                )
                for k, v in row.items()
            }
            out[canon] = clean_row
    _train_class_ref_by_folder = out
    return out


def candidates_from_yolo_master_class_probs(
    route_result: Dict[str, Any],
    top_k: int,
) -> List[Dict[str, Any]]:
    """
    라우터 모델이 raw/packaged/other 가 아닌 ing_XXXXX (학습 폴더명) 만 줄 때:
    softmax `probabilities` 상위 top_k 를 마스터 JSON과 붙여 recognizedCandidates 생성.
    """
    probs = route_result.get("probabilities") or {}
    if not isinstance(probs, dict) or not probs:
        return []

    ing_like = sum(1 for k in probs if isinstance(k, str) and _ING_CLASS_KEY.match(k.strip()))
    if ing_like < 1:
        return []

    # softmax 키를 canonical ing_XXXXX 로 합침 (ing_7 vs ing_00007 중복 방지)
    merged: Dict[str, float] = {}
    for k, v in probs.items():
        if not isinstance(k, str) or not _ING_CLASS_KEY.match(k.strip()):
            continue
        ck = _canonical_ing_folder_key(k)
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        merged[ck] = merged.get(ck, 0.0) + fv

    ranked = sorted(merged.items(), key=lambda x: x[1], reverse=True)[:top_k]
    if not ranked:
        return []

    label_map = _load_master_train_label_map()
    csv_map = _load_train_class_reference_map()
    raw: List[Dict[str, Any]] = []
    for canon_key, conf in ranked:
        entry = label_map.get(canon_key) if isinstance(label_map, dict) else None
        if isinstance(entry, dict):
            iid = entry.get("ingredientId")
            try:
                mid = int(iid) if iid is not None else None
            except (TypeError, ValueError):
                mid = None
            raw.append(
                {
                    "displayName": str(entry.get("displayName") or canon_key),
                    "normalizedName": str(
                        entry.get("normalizedName")
                        or entry.get("displayName")
                        or canon_key
                    ),
                    "categorySuggestion": str(entry.get("categorySuggestion") or ""),
                    "confidence": conf,
                    "modelLabel": canon_key,
                    "ingredientMasterId": mid,
                }
            )
            continue

        row = csv_map.get(canon_key)
        if row:
            try:
                mid = int(row.get("ingredient_id") or 0) or None
            except (TypeError, ValueError):
                mid = None
            dn = str(row.get("display_name") or canon_key)
            nn = str(row.get("normalized_name") or dn)
            raw.append(
                {
                    "displayName": dn,
                    "normalizedName": nn,
                    "categorySuggestion": "",
                    "confidence": conf,
                    "modelLabel": canon_key,
                    "ingredientMasterId": mid,
                }
            )
        else:
            raw.append(
                {
                    "displayName": canon_key,
                    "normalizedName": canon_key,
                    "categorySuggestion": "",
                    "confidence": conf,
                    "modelLabel": canon_key,
                }
            )
    return normalize_candidates(raw, default_category=None)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _candidate_confidence_value(candidate: Dict[str, Any]) -> float:
    try:
        return float(candidate.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def sort_candidates_by_model_confidence(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """UI는 모델 softmax( confidence ) 높은 순이 자연스러움. 임베딩 리랭크는 순서만 바꾸고 confidence 는 유지되므로 마지막에 정렬."""
    if len(candidates) <= 1:
        return candidates
    return sorted(candidates, key=_candidate_confidence_value, reverse=True)


def _candidate_name_text(candidate: Dict[str, Any]) -> str:
    return str(candidate.get("normalizedName") or candidate.get("displayName") or "").strip()


def _build_embedding_query_text(route: str, candidates: List[Dict[str, Any]]) -> str:
    if not candidates:
        return ""

    if route == "packaged_food":
        ocr_texts: List[str] = []
        for c in candidates:
            t = str(c.get("ocrText") or "").strip()
            if t:
                ocr_texts.append(t)
        if ocr_texts:
            return " ".join(ocr_texts)

    # raw_ingredient 또는 OCR 텍스트가 없는 경우에는 top1 후보명을 query로 사용
    return _candidate_name_text(candidates[0])


def rerank_candidates_with_embedding(route: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(candidates) <= 1:
        return candidates

    query_text = _build_embedding_query_text(route, candidates)
    if not query_text:
        return candidates

    try:
        query_vec = generate_embedding(query_text)
        if not isinstance(query_vec, list) or len(query_vec) == 0:
            return candidates

        scored: List[Dict[str, Any]] = []
        for idx, cand in enumerate(candidates):
            name_text = _candidate_name_text(cand)
            if not name_text:
                scored.append({"idx": idx, "score": -1.0})
                continue
            cand_vec = generate_embedding(name_text)
            if not isinstance(cand_vec, list) or len(cand_vec) == 0:
                scored.append({"idx": idx, "score": -1.0})
                continue
            sim = _cosine_similarity(query_vec, cand_vec)
            # 기존 confidence를 소폭 가중해 동점/근접 점수에서 모델 출력을 존중
            conf = float(cand.get("confidence") or 0.0)
            final_score = (sim * 0.8) + (conf * 0.2)
            scored.append({"idx": idx, "score": final_score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return [candidates[s["idx"]] for s in scored]
    except Exception:
        return candidates


def _extract_route_fields(route_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    route classifier 결과를 구/신 스키마 모두에서 안전하게 읽는다.

    - 구 스키마: {"route": "raw_ingredient", "confidence": 0.9, ...}
    - 신 스키마: {"route": {"type": "raw_ingredient", "confidence": 0.9, ...}, ...}
    """
    route_obj = route_result.get("route")

    if isinstance(route_obj, dict):
        route = str(route_obj.get("type") or "unknown")
        route_confidence = float(route_obj.get("confidence", 0.0) or 0.0)
        route_needs_review = bool(route_obj.get("needsReview", True))
        route_reason = route_obj.get("reason")
        probs = route_obj.get("probabilities", {})
        route_probabilities = probs if isinstance(probs, dict) else {}
        return {
            "route": route,
            "confidence": route_confidence,
            "needs_user_confirmation": route_needs_review,
            "reason": route_reason,
            "probabilities": route_probabilities,
        }

    route = str(route_obj or "unknown")
    route_confidence = float(route_result.get("confidence", 0.0) or 0.0)
    route_needs_review = bool(route_result.get("needs_user_confirmation", True))
    route_reason = route_result.get("reason")
    probs = route_result.get("probabilities", {})
    route_probabilities = probs if isinstance(probs, dict) else {}
    return {
        "route": route,
        "confidence": route_confidence,
        "needs_user_confirmation": route_needs_review,
        "reason": route_reason,
        "probabilities": route_probabilities,
    }


def normalize_candidates(raw_result: Any, default_category: Optional[str]) -> List[Dict[str, Any]]:
    """
    후속 OCR/classifier 모듈의 반환 형태가 조금 달라도
    API 문서의 recognizedCandidates 형태로 맞춘다.

    허용:
    - str
    - dict
    - list[str]
    - list[dict]
    """
    if raw_result is None:
        return []

    if isinstance(raw_result, str):
        name = raw_result.strip()
        if not name:
            return []
        return [
            {
                "displayName": name,
                "normalizedName": name,
                "categorySuggestion": default_category,
                "confidence": 0.0,
                "bbox": None,
            }
        ]

    if isinstance(raw_result, dict):
        return [candidate_dict_to_contract(raw_result, default_category)]

    if isinstance(raw_result, list):
        candidates: List[Dict[str, Any]] = []
        for item in raw_result:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    candidates.append(
                        {
                            "displayName": name,
                            "normalizedName": name,
                            "categorySuggestion": default_category,
                            "confidence": 0.0,
                            "bbox": None,
                        }
                    )
            elif isinstance(item, dict):
                candidates.append(candidate_dict_to_contract(item, default_category))
        return candidates

    return []


def candidate_dict_to_contract(item: Dict[str, Any], default_category: Optional[str]) -> Dict[str, Any]:
    display_name = (
        item.get("displayName")
        or item.get("display_name")
        or item.get("name")
        or item.get("rawName")
        or item.get("raw_name")
        or ""
    )

    normalized_name = (
        item.get("normalizedName")
        or item.get("normalized_name")
        or item.get("normalized")
        or display_name
    )

    confidence = item.get("confidence", item.get("score", 0.0))

    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    out: Dict[str, Any] = {
        "displayName": str(display_name),
        "normalizedName": str(normalized_name),
        "categorySuggestion": item.get("categorySuggestion")
        or item.get("category_suggestion")
        or item.get("category")
        or default_category,
        "confidence": confidence,
        "bbox": item.get("bbox"),
    }
    imid = item.get("ingredientMasterId", item.get("ingredient_master_id", item.get("ingredientId")))
    if imid is not None:
        try:
            out["ingredientMasterId"] = int(imid)
        except (TypeError, ValueError):
            pass
    ml = item.get("modelLabel", item.get("model_label"))
    if ml is not None and str(ml).strip():
        out["modelLabel"] = str(ml).strip()
    rml = item.get("resolvedModelLabel", item.get("resolved_model_label"))
    if rml is not None and str(rml).strip():
        out["resolvedModelLabel"] = str(rml).strip()
    if "predictionUncertain" in item:
        out["predictionUncertain"] = bool(item["predictionUncertain"])
    if item.get("top1Top2Margin") is not None:
        try:
            out["top1Top2Margin"] = float(item["top1Top2Margin"])
        except (TypeError, ValueError):
            pass
    if "ttaAveraged" in item:
        out["ttaAveraged"] = bool(item["ttaAveraged"])
    return out


@router.get("/system/health")
def health(
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
) -> Dict[str, Any]:
    request_id = make_request_id(x_request_id)

    route_model_path = os.getenv("INGREDIENT_ROUTE_MODEL_PATH", DEFAULT_ROUTE_MODEL_PATH)
    route_model_exists = Path(route_model_path).exists()

    raw_model_path = os.getenv("RAW_INGREDIENT_MODEL_PATH", "app/models/ingredient/weights/raw_ingredient_best.pt")
    raw_vocab_path = os.getenv(
        "RAW_INGREDIENT_VOCAB_PATH",
        "app/models/ingredient/data/ingredient_normalized_vocab.json",
    )
    raw_label_map_path = os.getenv(
        "RAW_INGREDIENT_LABEL_MAP_PATH",
        "app/models/ingredient/data/model_label_to_master.json",
    )

    return common_success(
        code="OK",
        message="service healthy" if route_model_exists else "service degraded",
        request_id=request_id,
        data={
            "status": "ok" if route_model_exists else "degraded",
            "service": "fastapi-analysis",
            "checks": {
                "ingredientRouteModelPath": route_model_path,
                "ingredientRouteModelExists": route_model_exists,
                "ingredientRouteModelLoaded": _route_classifier is not None,
                "ingredientRouteModelLoadError": _route_classifier_load_error,
                "rawIngredientModelPath": raw_model_path,
                "rawIngredientModelExists": Path(raw_model_path).exists(),
                "rawIngredientVocabPath": raw_vocab_path,
                "rawIngredientVocabExists": Path(raw_vocab_path).exists(),
                "rawIngredientLabelMapPath": raw_label_map_path,
                "rawIngredientLabelMapExists": Path(raw_label_map_path).exists(),
                "packagedFoodOcrAdapter": "app.models.ocr.packagedFoodOcr.recognize_packaged_food_image",
                "rawIngredientClassifierAdapter": "app.models.ingredient.rawIngredientClassifier.recognize_raw_ingredient_image",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.post("/vision/recognize-ingredient-image")
async def recognize_ingredient_image(
    file: UploadFile = File(...),
    topK: int = Form(default=MAX_RECOGNITION_CANDIDATES),
    detectMultiple: bool = Form(default=False),
    source: Optional[str] = Form(default=None),
    x_internal_service: Optional[str] = Header(default=None, alias="X-Internal-Service"),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
) -> Dict[str, Any]:
    request_id = make_request_id(x_request_id)

    verify_internal_call(
        x_internal_service=x_internal_service,
        x_internal_token=x_internal_token,
        request_id=request_id,
    )

    if file.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        return common_error(
            code="UNSUPPORTED_MEDIA_TYPE",
            message=f"unsupported image type: {file.content_type}",
            request_id=request_id,
            errors=[
                {
                    "field": "file",
                    "reason": "only image/jpeg, image/png, image/webp are allowed",
                }
            ],
        )

    if topK < 1 or topK > 10:
        return common_error(
            code="INTERNAL_VALIDATION_ERROR",
            message="invalid topK",
            request_id=request_id,
            errors=[
                {
                    "field": "topK",
                    "reason": "must be between 1 and 10",
                }
            ],
        )
    effective_top_k = min(topK, MAX_RECOGNITION_CANDIDATES)
    # 현재 UI 정책은 단일 이미지/단일 물체 전제.
    # detectMultiple=true가 들어와도 endpoint는 단일 처리로 동작하고 meta에 기록한다.
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"

    temp_path: Optional[Path] = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            temp_path = Path(tmp.name)

        route = "packaged_food"
        route_confidence = 1.0
        route_needs_review = False
        route_reason = "ocr-first pipeline: packaged_food OCR attempted first."
        route_probabilities: Dict[str, float] = {}

        candidates: List[Dict[str, Any]] = []
        pipeline_stage = "packaged_food_ocr_first"
        ocr_error: Optional[str] = None

        try:
            candidates = recognize_packaged_food_by_ocr(temp_path, effective_top_k)
        except Exception as exc:
            ocr_error = str(exc)
            candidates = []

        if not candidates:
            pipeline_stage = "raw_ingredient_classifier_fallback"
            raw_candidates = recognize_raw_ingredient_by_classifier(temp_path, effective_top_k)
            if raw_candidates:
                route = "raw_ingredient"
                route_confidence = float(raw_candidates[0].get("confidence", 0.0) or 0.0)
                route_reason = (
                    "ocr-first fallback applied: raw ingredient classifier used because OCR "
                    f"{'failed' if ocr_error else 'returned empty'}."
                )
                candidates = raw_candidates
            else:
                route = "unknown"
                route_confidence = 0.0
                route_needs_review = True
                route_reason = (
                    "ocr-first pipeline: OCR and raw ingredient fallback both produced no candidates."
                )

        embedding_rerank_applied = False
        if _env_bool("VISION_EMBEDDING_RERANK_ENABLED", EMBEDDING_RERANK_ENABLED_DEFAULT):
            reordered = rerank_candidates_with_embedding(route=route, candidates=candidates)
            embedding_rerank_applied = reordered is not candidates
            candidates = reordered

        # 임베딩 리랭크 후에도 표시는 모델 confidence 내림차순 (사용자 기대: 높은 확률이 위)
        candidates = sort_candidates_by_model_confidence(candidates)[:effective_top_k]

        # 후보가 없으면 Spring Boot가 사용자 수동 입력/확인을 유도할 수 있게 needsReview를 true로 둔다.
        # 비포장 분류: 불확실(1·2위 근접·낮은 신뢰도)도 검토 유도.
        first_uncertain = bool(candidates[0].get("predictionUncertain")) if candidates else False
        needs_review = route_needs_review or len(candidates) == 0 or first_uncertain

        dl_analysis = compute_dl_anomaly_analysis(temp_path)
        anomaly_analysis = build_anomaly_analysis(
            route=route,
            route_confidence=route_confidence,
            route_needs_review=route_needs_review,
            candidates=candidates,
            pipeline_stage=pipeline_stage,
            needs_review=needs_review,
            dl_analysis=dl_analysis,
        )

        return common_success(
            code="OK",
            message="recognized",
            request_id=request_id,
            data={
                "recognizedCandidates": candidates[:effective_top_k],
                "route": {
                    "type": route,
                    "confidence": route_confidence,
                    "needsReview": route_needs_review,
                    "reason": route_reason,
                    "probabilities": route_probabilities,
                },
                "pipeline": {
                    "stage": pipeline_stage,
                    "source": source,
                    "detectMultipleRequested": detectMultiple,
                    "effectiveDetectMultiple": False,
                    "requestedTopK": topK,
                    "effectiveTopK": effective_top_k,
                    "embeddingRerankApplied": embedding_rerank_applied,
                },
                "needsReview": needs_review,
                "anomalyAnalysis": anomaly_analysis,
            },
        )

    except HTTPException:
        raise

    except RuntimeError as exc:
        return common_error(
            code="MODEL_UNAVAILABLE",
            message=str(exc),
            request_id=request_id,
        )

    except Exception as exc:
        return common_error(
            code="MODEL_UNAVAILABLE",
            message=f"image recognition pipeline failed: {exc}",
            request_id=request_id,
        )

    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
