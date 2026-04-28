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

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


VALID_ROUTES = {"raw_ingredient", "packaged_food", "other"}


@dataclass
class RouteClassificationResult:
    image_path: str
    route: str
    confidence: float
    needs_user_confirmation: bool
    reason: str
    probabilities: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_path": self.image_path,
            "route": self.route,
            "confidence": self.confidence,
            "needs_user_confirmation": self.needs_user_confirmation,
            "reason": self.reason,
            "probabilities": self.probabilities,
        }


class IngredientRouteClassifier:
    """
    YOLO classification 기반 식재료 라우터.

    Parameters
    ----------
    model_path:
        학습된 YOLO classify best.pt 경로.
        예: runs/classify/train/weights/best.pt

    confidence_threshold:
        이 값보다 낮으면 사용자 확인이 필요하다고 표시한다.
        MVP 시작값은 0.60 추천.

    device:
        None이면 ultralytics가 자동 선택.
        CPU: "cpu"
        Mac MPS: "mps"
        CUDA: "0"

    imgsz:
        추론 이미지 크기.
        학습 때 imgsz=224를 썼다면 추론도 224를 권장.
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
                "학습 결과 폴더에서 best.pt 경로를 확인하세요.\n"
                "예: find runs/classify -name best.pt"
            )

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                "ultralytics가 설치되어 있지 않습니다.\n"
                "설치: pip install ultralytics"
            ) from exc

        self.model = YOLO(str(self.model_path))

    def classify_image(self, image_path: str | Path) -> Dict[str, Any]:
        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        results = self.model.predict(
            source=str(image_path),
            imgsz=self.imgsz,
            device=self.device,
            verbose=False,
        )

        if not results:
            return RouteClassificationResult(
                image_path=str(image_path),
                route="unknown",
                confidence=0.0,
                needs_user_confirmation=True,
                reason="YOLO classification 결과가 비어 있습니다.",
                probabilities={},
            ).to_dict()

        result = results[0]
        probs = getattr(result, "probs", None)
        names = getattr(result, "names", None) or getattr(self.model, "names", None)

        if probs is None:
            return RouteClassificationResult(
                image_path=str(image_path),
                route="unknown",
                confidence=0.0,
                needs_user_confirmation=True,
                reason="classification 확률 정보(probs)가 없습니다. detect 모델을 넣은 것은 아닌지 확인하세요.",
                probabilities={},
            ).to_dict()

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
            return RouteClassificationResult(
                image_path=str(image_path),
                route="unknown",
                confidence=top1_conf,
                needs_user_confirmation=True,
                reason=f"모델이 알 수 없는 class를 반환했습니다: {label}",
                probabilities=probabilities,
            ).to_dict()

        needs_user_confirmation = top1_conf < self.confidence_threshold

        if needs_user_confirmation:
            reason = (
                f"{route}로 분류되었지만 confidence가 낮습니다. "
                f"현재 {top1_conf:.3f}, 기준 {self.confidence_threshold:.3f}"
            )
        else:
            reason = f"{route}로 분류되었습니다."

        return RouteClassificationResult(
            image_path=str(image_path),
            route=route,
            confidence=top1_conf,
            needs_user_confirmation=needs_user_confirmation,
            reason=reason,
            probabilities=probabilities,
        ).to_dict()

    def _extract_probabilities(self, probs: Any, names: Any) -> Dict[str, float]:
        """
        전체 class별 확률을 dict로 반환한다.
        Ultralytics 내부 tensor가 torch/numpy 어느 쪽이든 처리한다.
        """
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
