"""
ingredient_route_cls_classifier.py

YOLO classification 기반 식재료/포장식품 1차 라우팅 모듈.

전제:
- 단일 물체 이미지를 입력한다.
- 학습된 YOLO classify 모델(best.pt)을 사용한다.
- 모델 class 폴더명은 다음 중 일부/전체여야 한다.
    raw_ingredient
    packaged_food
    other

역할:
- 이미지 1장을 받아 route와 confidence를 반환한다.
- box 좌표는 반환하지 않는다. classification 모델이므로 box가 없다.
- OCR과 세부 식재료 인식은 하지 않는다.

설치:
    pip install ultralytics pillow

사용 예시:
    from ingredient_route_cls_classifier import IngredientRouteClassifier

    classifier = IngredientRouteClassifier(
        model_path="runs/classify/train/weights/best.pt",
        confidence_threshold=0.60,
    )

    result = classifier.classify_image("sample.jpg")
    print(result)

CLI:
    python ingredient_route_cls_classifier.py \
      --image sample.jpg \
      --model runs/classify/train/weights/best.pt
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# 상세 인식을 위한 모듈 임포트
try:
    from app.models.ocr.packagedFoodOcr import recognize_packaged_food_image
    from app.models.ingredient.rawIngredientClassifier import recognize_raw_ingredient_image
except ImportError:
    # 직접 실행 시 sys.path 설정이 필요할 수 있음
    import sys
    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    from app.models.ocr.packagedFoodOcr import recognize_packaged_food_image
    from app.models.ingredient.rawIngredientClassifier import recognize_raw_ingredient_image


VALID_ROUTES = {"raw_ingredient", "packaged_food", "other"}


@dataclass
class RouteClassificationResult:
    image_path: str
    route: str
    confidence: float
    needs_user_confirmation: bool
    reason: str
    probabilities: Dict[str, float]
    recognized_candidates: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_path": self.image_path,
            "route": self.route,
            "confidence": self.confidence,
            "needs_user_confirmation": self.needs_user_confirmation,
            "reason": self.reason,
            "probabilities": self.probabilities,
            "recognizedCandidates": self.recognized_candidates,
        }


class IngredientRouteClassifier:
    """
    YOLO classification 기반 식재료 라우터 + 상세 인식 통합 모듈.
    """

    def __init__(
        self,
        model_path: str | Path,
        confidence_threshold: float = 0.60,
        device: Optional[str] = None,
        imgsz: int = 224,
    ) -> None:
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold
        self.device = device
        self.imgsz = imgsz

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"모델 파일을 찾을 수 없습니다: {self.model_path}\n"
                "학습 결과 폴더에서 best.pt 경로를 확인하세요."
            )

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                f"ultralytics import 실패: {repr(exc)}"
            ) from exc

        self.model = YOLO(str(self.model_path))

    def classify_image(self, image_path: str | Path) -> Dict[str, Any]:
        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        # 1. 라우팅 분류 (Packaged vs Raw)
        results = self.model.predict(
            source=str(image_path),
            imgsz=self.imgsz,
            device=self.device,
            verbose=False,
        )

        if not results:
            return self._make_error_result(str(image_path), "YOLO classification 결과가 비어 있습니다.")

        result = results[0]
        probs = getattr(result, "probs", None)
        names = getattr(result, "names", None) or getattr(self.model, "names", None)

        if probs is None:
            return self._make_error_result(str(image_path), "classification 확률 정보(probs)가 없습니다.")

        top1_id = int(probs.top1)
        top1_conf = float(probs.top1conf)

        if isinstance(names, dict):
            label = str(names.get(top1_id, top1_id))
        elif isinstance(names, list) and 0 <= top1_id < len(names):
            label = str(names[top1_id])
        else:
            label = str(top1_id)

        route = self._normalize_route(label)
        probabilities = self._extract_probabilities(probs=probs, names=names)

        if route not in VALID_ROUTES:
            return self._make_error_result(str(image_path), f"알 수 없는 class: {label}", route="unknown", conf=top1_conf, probs=probabilities)

        needs_user_confirmation = top1_conf < self.confidence_threshold
        reason = self._build_reason(route, top1_conf, needs_user_confirmation)

        # 2. 라우팅 결과에 따른 상세 인식 수행
        candidates = []
        try:
            if route == "packaged_food":
                candidates = recognize_packaged_food_image(image_path, top_k=5)
            elif route == "raw_ingredient":
                candidates = recognize_raw_ingredient_image(image_path, top_k=5)
        except Exception as e:
            # 상세 인식 실패 시 로그 출력 후 빈 결과 유지 (라우팅 정보는 제공)
            print(f"[RECOGNITION ERROR] {route} 인식 중 오류 발생: {e}")

        return RouteClassificationResult(
            image_path=str(image_path),
            route=route,
            confidence=top1_conf,
            needs_user_confirmation=needs_user_confirmation,
            reason=reason,
            probabilities=probabilities,
            recognized_candidates=candidates,
        ).to_dict()

    def _make_error_result(self, image_path: str, message: str, route: str = "unknown", conf: float = 0.0, probs: Dict[str, float] = None) -> Dict[str, Any]:
        return RouteClassificationResult(
            image_path=image_path,
            route=route,
            confidence=conf,
            needs_user_confirmation=True,
            reason=message,
            probabilities=probs or {},
            recognized_candidates=[],
        ).to_dict()

    def _build_reason(self, route: str, conf: float, needs_review: bool) -> str:
        if needs_review:
            return (
                f"{route}로 분류되었지만 confidence가 낮습니다. "
                f"현재 {conf:.3f}, 기준 {self.confidence_threshold:.3f}"
            )
        return f"{route}로 분류되었습니다."

    def _extract_probabilities(self, probs: Any, names: Any) -> Dict[str, float]:
        data = getattr(probs, "data", None)
        if data is None:
            return {}

        try:
            values = data.detach().cpu().tolist()
        except AttributeError:
            try:
                values = data.cpu().tolist()
            except AttributeError:
                try:
                    values = data.tolist()
                except AttributeError:
                    return {}

        output: Dict[str, float] = {}
        for idx, value in enumerate(values):
            if isinstance(names, dict):
                label = str(names.get(idx, idx))
            elif isinstance(names, list) and 0 <= idx < len(names):
                label = str(names[idx])
            else:
                label = str(idx)
            output[self._normalize_route(label)] = float(value)
        return output

    @staticmethod
    def _normalize_route(label: str) -> str:
        return label.strip().lower().replace("-", "_").replace(" ", "_")


def classify_image(
    image_path: str | Path,
    model_path: str | Path,
    confidence_threshold: float = 0.60,
    device: Optional[str] = None,
    imgsz: int = 224,
) -> Dict[str, Any]:
    """
    단발성 호출용 함수.

    여러 장을 처리할 때는 IngredientRouteClassifier 객체를 한 번 만들고
    classifier.classify_image(...)를 반복 호출하는 게 더 효율적이다.
    """
    classifier = IngredientRouteClassifier(
        model_path=model_path,
        confidence_threshold=confidence_threshold,
        device=device,
        imgsz=imgsz,
    )
    return classifier.classify_image(image_path)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="YOLO classification 기반 식재료/포장식품 라우팅")
    parser.add_argument("--image", required=True, help="입력 이미지 경로")
    parser.add_argument("--model", required=True, help="학습된 classify best.pt 경로")
    parser.add_argument("--threshold", type=float, default=0.60, help="사용자 확인 기준 confidence")
    parser.add_argument("--device", default=None, help='예: "cpu", "mps", "0"')
    parser.add_argument("--imgsz", type=int, default=224, help="추론 이미지 크기")

    args = parser.parse_args()

    result = classify_image(
        image_path=args.image,
        model_path=args.model,
        confidence_threshold=args.threshold,
        device=args.device,
        imgsz=args.imgsz,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
