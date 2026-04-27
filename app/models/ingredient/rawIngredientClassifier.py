"""
rawIngredientClassifier.py

raw_ingredient 이미지용 실제 식재료 분류 모듈.

역할:
- 이미 1차 라우터에서 raw_ingredient로 판정된 단일 물체 이미지를 입력받는다.
- YOLO classification 모델로 실제 식재료 후보를 topK개 반환한다.
- 내부 API의 recognizedCandidates 계약에 맞는 list[dict]를 반환한다.

주의:
- 이 파일은 OCR을 다루지 않는다.
- packaged_food 경로는 민예린 씨의 OCR 모듈에서 담당한다.
- 이 파일은 "세부 식재료 분류 모델"의 추론 wrapper다.
- 실제 동작에는 raw 식재료 클래스로 학습한 best.pt가 필요하다.

권장 모델 위치:
    app/models/ingredient/weights/raw_ingredient_best.pt

필수 함수:
    recognize_raw_ingredient_image(image_path, top_k=5)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_MODEL_PATH = "app/models/ingredient/weights/raw_ingredient_best.pt"

INGREDIENT_LABEL_MAP: Dict[str, Dict[str, str]] = {
    "apple": {"displayName": "사과", "normalizedName": "사과", "categorySuggestion": "과일"},
    "pear": {"displayName": "배", "normalizedName": "배", "categorySuggestion": "과일"},
    "avocado": {"displayName": "아보카도", "normalizedName": "아보카도", "categorySuggestion": "과일"},
    "pomegranate": {"displayName": "석류", "normalizedName": "석류", "categorySuggestion": "과일"},
    "kiwi": {"displayName": "키위", "normalizedName": "키위", "categorySuggestion": "과일"},
    "lemon": {"displayName": "레몬", "normalizedName": "레몬", "categorySuggestion": "과일"},
    "plum": {"displayName": "자두", "normalizedName": "자두", "categorySuggestion": "과일"},
    "nectarine": {"displayName": "천도복숭아", "normalizedName": "천도복숭아", "categorySuggestion": "과일"},
    "red_grapefruit": {"displayName": "자몽", "normalizedName": "자몽", "categorySuggestion": "과일"},
    "lime": {"displayName": "라임", "normalizedName": "라임", "categorySuggestion": "과일"},
    "mango": {"displayName": "망고", "normalizedName": "망고", "categorySuggestion": "과일"},
    "passion_fruit": {"displayName": "패션프루트", "normalizedName": "패션프루트", "categorySuggestion": "과일"},
    "banana": {"displayName": "바나나", "normalizedName": "바나나", "categorySuggestion": "과일"},
    "papaya": {"displayName": "파파야", "normalizedName": "파파야", "categorySuggestion": "과일"},
    "satsumas": {"displayName": "귤", "normalizedName": "귤", "categorySuggestion": "과일"},
    "pineapple": {"displayName": "파인애플", "normalizedName": "파인애플", "categorySuggestion": "과일"},
    "melon": {"displayName": "멜론", "normalizedName": "멜론", "categorySuggestion": "과일"},
    "orange": {"displayName": "오렌지", "normalizedName": "오렌지", "categorySuggestion": "과일"},
    "peach": {"displayName": "복숭아", "normalizedName": "복숭아", "categorySuggestion": "과일"},

    "mushroom": {"displayName": "버섯", "normalizedName": "버섯", "categorySuggestion": "채소"},
    "brown_cap_mushroom": {"displayName": "양송이버섯", "normalizedName": "양송이버섯", "categorySuggestion": "채소"},
    "onion": {"displayName": "양파", "normalizedName": "양파", "categorySuggestion": "채소"},
    "potato": {"displayName": "감자", "normalizedName": "감자", "categorySuggestion": "채소"},
    "cucumber": {"displayName": "오이", "normalizedName": "오이", "categorySuggestion": "채소"},
    "carrots": {"displayName": "당근", "normalizedName": "당근", "categorySuggestion": "채소"},
    "carrot": {"displayName": "당근", "normalizedName": "당근", "categorySuggestion": "채소"},
    "red_beet": {"displayName": "비트", "normalizedName": "비트", "categorySuggestion": "채소"},
    "cabbage": {"displayName": "양배추", "normalizedName": "양배추", "categorySuggestion": "채소"},
    "asparagus": {"displayName": "아스파라거스", "normalizedName": "아스파라거스", "categorySuggestion": "채소"},
    "ginger": {"displayName": "생강", "normalizedName": "생강", "categorySuggestion": "채소"},
    "zucchini": {"displayName": "주키니", "normalizedName": "주키니", "categorySuggestion": "채소"},
    "garlic": {"displayName": "마늘", "normalizedName": "마늘", "categorySuggestion": "채소"},
    "pepper": {"displayName": "파프리카", "normalizedName": "파프리카", "categorySuggestion": "채소"},
    "aubergine": {"displayName": "가지", "normalizedName": "가지", "categorySuggestion": "채소"},
    "tomato": {"displayName": "토마토", "normalizedName": "토마토", "categorySuggestion": "채소"},
    "leek": {"displayName": "대파", "normalizedName": "대파", "categorySuggestion": "채소"},
}


@dataclass
class RawIngredientCandidate:
    displayName: str
    normalizedName: str
    categorySuggestion: Optional[str]
    confidence: float
    bbox: None = None
    modelLabel: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "displayName": self.displayName,
            "normalizedName": self.normalizedName,
            "categorySuggestion": self.categorySuggestion,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "modelLabel": self.modelLabel,
        }


class RawIngredientClassifier:
    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        confidence_threshold: float = 0.20,
        device: Optional[str] = None,
        imgsz: int = 224,
    ) -> None:
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold
        self.device = device
        self.imgsz = imgsz

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"raw ingredient model 파일을 찾을 수 없습니다: {self.model_path}\n"
                "먼저 raw 식재료 분류 모델을 학습하고 best.pt를 해당 위치에 복사하세요."
            )

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError("ultralytics가 설치되어 있지 않습니다. 설치: pip install ultralytics") from exc

        self.model = YOLO(str(self.model_path))

    def recognize(self, image_path: str | Path, top_k: int = 5) -> List[Dict[str, Any]]:
        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        top_k = max(1, int(top_k))

        results = self.model.predict(
            source=str(image_path),
            imgsz=self.imgsz,
            device=self.device,
            verbose=False,
        )

        if not results:
            return []

        result = results[0]
        probs = getattr(result, "probs", None)
        names = getattr(result, "names", None) or getattr(self.model, "names", None)

        if probs is None:
            raise RuntimeError(
                "classification 확률 정보(probs)가 없습니다. raw ingredient 모델이 detect 모델인지 확인하세요."
            )

        candidates = self._topk_candidates(probs=probs, names=names, top_k=top_k)
        return [candidate.to_dict() for candidate in candidates]

    def _topk_candidates(self, probs: Any, names: Any, top_k: int) -> List[RawIngredientCandidate]:
        prob_values = self._prob_values(probs)
        if not prob_values:
            return []

        indexed = list(enumerate(prob_values))
        indexed.sort(key=lambda item: item[1], reverse=True)

        candidates: List[RawIngredientCandidate] = []

        for class_id, confidence in indexed[:top_k]:
            confidence = float(confidence)

            if confidence < self.confidence_threshold and candidates:
                continue

            label = self._label_from_id(names, class_id)
            normalized_label = normalize_label(label)
            meta = INGREDIENT_LABEL_MAP.get(normalized_label)

            if meta:
                display_name = meta["displayName"]
                normalized_name = meta["normalizedName"]
                category = meta["categorySuggestion"]
            else:
                display_name = label
                normalized_name = label
                category = None

            candidates.append(
                RawIngredientCandidate(
                    displayName=display_name,
                    normalizedName=normalized_name,
                    categorySuggestion=category,
                    confidence=confidence,
                    bbox=None,
                    modelLabel=label,
                )
            )

        return candidates

    @staticmethod
    def _prob_values(probs: Any) -> List[float]:
        data = getattr(probs, "data", None)
        if data is None:
            return []

        try:
            return [float(v) for v in data.detach().cpu().tolist()]
        except AttributeError:
            try:
                return [float(v) for v in data.cpu().tolist()]
            except AttributeError:
                try:
                    return [float(v) for v in data.tolist()]
                except AttributeError:
                    return []

    @staticmethod
    def _label_from_id(names: Any, class_id: int) -> str:
        if isinstance(names, dict):
            return str(names.get(class_id, class_id))
        if isinstance(names, list) and 0 <= class_id < len(names):
            return str(names[class_id])
        return str(class_id)


_classifier: Optional[RawIngredientClassifier] = None


def get_raw_ingredient_classifier() -> RawIngredientClassifier:
    global _classifier

    if _classifier is not None:
        return _classifier

    model_path = os.getenv("RAW_INGREDIENT_MODEL_PATH", DEFAULT_MODEL_PATH)
    threshold = float(os.getenv("RAW_INGREDIENT_CONFIDENCE_THRESHOLD", "0.20"))
    device = os.getenv("RAW_INGREDIENT_DEVICE") or os.getenv("INGREDIENT_ROUTE_DEVICE") or None
    imgsz = int(os.getenv("RAW_INGREDIENT_IMGSZ", "224"))

    _classifier = RawIngredientClassifier(
        model_path=model_path,
        confidence_threshold=threshold,
        device=device,
        imgsz=imgsz,
    )
    return _classifier


def recognize_raw_ingredient_image(
    image_path: str | Path,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    classifier = get_raw_ingredient_classifier()
    return classifier.recognize(image_path=image_path, top_k=top_k)


def normalize_label(label: str) -> str:
    return str(label).strip().lower().replace("-", "_").replace(" ", "_")


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="raw ingredient image classifier")
    parser.add_argument("--image", required=True, help="입력 이미지 경로")
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH, help="raw ingredient best.pt 경로")
    parser.add_argument("--topK", type=int, default=5)
    parser.add_argument("--device", default=None, help='예: "cpu", "mps", "0"')
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--threshold", type=float, default=0.20)

    args = parser.parse_args()

    clf = RawIngredientClassifier(
        model_path=args.model,
        confidence_threshold=args.threshold,
        device=args.device,
        imgsz=args.imgsz,
    )

    output = clf.recognize(args.image, top_k=args.topK)
    print(json.dumps(output, ensure_ascii=False, indent=2))
