"""
packagedFoodOcr.py

PaddleOCR 기반 포장식품 OCR 모듈 v3.

v2와의 차이:
- OCR은 성공했지만 '1등급', '세균수', '체세포수' 같은 품질/표기 문구가
  confidence가 높아 대표 후보로 올라오는 문제를 완화한다.
- OCR raw line은 전부 보존한다.
- displayName 후보만 product-title scoring으로 정렬한다.
- 정규화/DB 매칭은 하지 않는다. 이 파일은 OCR + 제목 후보 추출까지만 담당한다.

권장 위치:
    app/models/ocr/packagedFoodOcr.py

필수 함수:
    recognize_packaged_food_image(image_path, top_k=5)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image


DEFAULT_OCR_LANG = "korean"


# 상품명 후보에서 감점할 가능성이 큰 포장/품질/영양/제조 표기.
# 이건 식재료 정규화 규칙이 아니라 OCR title ranking용 노이즈 필터다.
NOISE_PATTERNS = [
    r"\d+\s*등급",
    r"\d+[A-Za-z]\s*등급",
    r"세균수",
    r"세군수",
    r"체세포수",
    r"냉장제품",
    r"냉장",
    r"냉동",
    r"kcal",
    r"칼로리",
    r"\d+\s*m[lL]",
    r"\d+\s*ml",
    r"\d+\s*g",
    r"\d+\s*kg",
    r"\d+\s*%",
    r"\d{1,2}\.\d{1,2}\.?",
    r"\d{2,4}[./-]\d{1,2}[./-]\d{1,2}",
    r"까지",
    r"제조",
    r"유통",
    r"소비기한",
    r"보관",
    r"주의",
    r"원재료",
    r"영양정보",
    r"나트륨",
    r"탄수화물",
    r"단백질",
    r"지방",
    r"당류",
    r"총내용량",
    r"내용량",
    r"원유",
    r"살균",
    r"멸균",
    r"R\d+",
    r"[A-Za-z0-9]{6,}",
]

# 상품/식품명 후보로 볼 때 가산할 키워드.
PRODUCT_KEYWORDS = [
    "우유",
    "서울우유",
    "매일",
    "남양",
    "빙그레",
    "쿨피스",
    "두유",
    "요구르트",
    "요거트",
    "주스",
    "쥬스",
    "두부",
    "라면",
    "고추장",
    "된장",
    "쌈장",
    "소스",
    "간장",
    "식초",
    "치즈",
    "버터",
    "크림",
    "햄",
    "소시지",
    "참치",
    "김치",
    "만두",
    "어묵",
    "떡",
    "음료",
    "생수",
]

# 너무 일반적인 단독 후보는 낮춘다. 단, 다른 브랜드/제품명과 결합되면 사용 가능.
WEAK_SINGLE_WORDS = {
    "우유",
    "두유",
    "주스",
    "쥬스",
    "요거트",
    "요구르트",
    "두부",
    "라면",
    "소스",
    "치즈",
    "버터",
    "크림",
}


@dataclass
class OcrLine:
    text: str
    confidence: float
    box: Optional[Any] = None
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "box": self.box,
            "score": self.score,
        }


@dataclass
class PackagedFoodCandidate:
    displayName: str
    normalizedName: str
    categorySuggestion: Optional[str]
    confidence: float
    bbox: Optional[Any]
    ocrText: str
    ocrLines: List[Dict[str, Any]]
    extractionReason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "displayName": self.displayName,
            "normalizedName": self.normalizedName,
            "categorySuggestion": self.categorySuggestion,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "ocrText": self.ocrText,
            "ocrLines": self.ocrLines,
            "extractionReason": self.extractionReason,
        }


class PackagedFoodOcr:
    def __init__(
        self,
        lang: str = DEFAULT_OCR_LANG,
        min_text_confidence: float = 0.30,
        max_merge_lines: int = 3,
        debug: bool = False,
    ) -> None:
        self.lang = lang
        self.min_text_confidence = min_text_confidence
        self.max_merge_lines = max_merge_lines
        self.debug = debug
        self.ocr = self._load_ocr()

    def recognize(self, image_path: str | Path, top_k: int = 5) -> List[Dict[str, Any]]:
        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        image = Image.open(image_path).convert("RGB")
        image_width, image_height = image.size

        raw_result = self._run_ocr(image_path)

        if self.debug:
            print("========== RAW OCR RESULT ==========")
            print(self._safe_json_dumps(self._raw_to_debuggable(raw_result)))
            print("====================================")

        lines = self._parse_ocr_result(raw_result)
        lines = self._score_lines(lines, image_size=(image_width, image_height))

        if self.debug:
            print("========== SCORED OCR LINES ==========")
            print(json.dumps([line.to_dict() for line in lines], ensure_ascii=False, indent=2))
            print("======================================")

        if not lines:
            return []

        candidates = self._build_candidates(lines=lines, top_k=top_k)

        if self.debug:
            print("========== CANDIDATES ==========")
            print(json.dumps([candidate.to_dict() for candidate in candidates], ensure_ascii=False, indent=2))
            print("================================")

        return [candidate.to_dict() for candidate in candidates[:top_k]]

    def _load_ocr(self) -> Any:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise ImportError(
                "paddleocr가 설치되어 있지 않습니다. 설치: pip install paddleocr paddlepaddle"
            ) from exc

        try:
            return PaddleOCR(
                lang=self.lang,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
            )
        except TypeError:
            try:
                return PaddleOCR(use_angle_cls=True, lang=self.lang)
            except TypeError:
                return PaddleOCR(lang=self.lang)

    def _run_ocr(self, image_path: Path) -> Any:
        if hasattr(self.ocr, "predict"):
            return self.ocr.predict(str(image_path))

        try:
            return self.ocr.ocr(str(image_path), cls=True)
        except TypeError:
            return self.ocr.ocr(str(image_path))

    def _parse_ocr_result(self, raw_result: Any) -> List[OcrLine]:
        lines: List[OcrLine] = []

        if isinstance(raw_result, list):
            for item in raw_result:
                parsed = self._parse_result_object(item)
                if parsed:
                    lines.extend(parsed)
                else:
                    self._parse_legacy_node(item, lines)
        else:
            parsed = self._parse_result_object(raw_result)
            if parsed:
                lines.extend(parsed)
            else:
                self._parse_legacy_node(raw_result, lines)

        return self._dedupe_lines(lines)

    def _parse_result_object(self, item: Any) -> List[OcrLine]:
        if item is None:
            return []

        json_obj = None

        if hasattr(item, "json"):
            try:
                json_obj = item.json
            except Exception:
                json_obj = None

        if json_obj is None and isinstance(item, dict):
            json_obj = item

        if not isinstance(json_obj, dict):
            return []

        res = json_obj.get("res", json_obj)
        if not isinstance(res, dict):
            return []

        texts = res.get("rec_texts") or []
        scores = res.get("rec_scores") or []
        boxes = res.get("rec_boxes") or res.get("rec_polys") or []

        parsed: List[OcrLine] = []

        if isinstance(texts, list):
            for idx, text in enumerate(texts):
                clean_text = clean_ocr_text(text)
                if not clean_text:
                    continue

                score = scores[idx] if isinstance(scores, list) and idx < len(scores) else 0.0
                box = boxes[idx] if hasattr(boxes, "__len__") and idx < len(boxes) else None

                parsed.append(
                    OcrLine(
                        text=clean_text,
                        confidence=safe_float(score, default=0.0),
                        box=to_jsonable(box),
                    )
                )

        single_text = res.get("rec_text")
        if isinstance(single_text, str) and single_text.strip():
            parsed.append(
                OcrLine(
                    text=clean_ocr_text(single_text),
                    confidence=safe_float(res.get("rec_score"), default=0.0),
                    box=to_jsonable(res.get("rec_box") or res.get("rec_poly")),
                )
            )

        return parsed

    def _parse_legacy_node(self, node: Any, lines: List[OcrLine]) -> None:
        if node is None:
            return

        if isinstance(node, dict):
            text = (
                node.get("rec_text")
                or node.get("text")
                or node.get("transcription")
                or node.get("label")
            )
            score = node.get("rec_score") or node.get("score") or node.get("confidence")
            box = node.get("dt_polys") or node.get("box") or node.get("points")

            if isinstance(text, str) and text.strip():
                lines.append(
                    OcrLine(
                        text=clean_ocr_text(text),
                        confidence=safe_float(score, default=0.0),
                        box=to_jsonable(box),
                    )
                )

            for value in node.values():
                if isinstance(value, (list, tuple, dict)):
                    self._parse_legacy_node(value, lines)
            return

        if (
            isinstance(node, list)
            and len(node) >= 2
            and isinstance(node[1], tuple)
            and len(node[1]) >= 1
            and isinstance(node[1][0], str)
        ):
            box = node[0]
            text = node[1][0]
            score = node[1][1] if len(node[1]) >= 2 else 0.0

            clean_text = clean_ocr_text(text)
            if clean_text:
                lines.append(
                    OcrLine(
                        text=clean_text,
                        confidence=safe_float(score, default=0.0),
                        box=to_jsonable(box),
                    )
                )
            return

        if isinstance(node, tuple):
            if len(node) >= 1 and isinstance(node[0], str):
                clean_text = clean_ocr_text(node[0])
                if clean_text:
                    lines.append(
                        OcrLine(
                            text=clean_text,
                            confidence=safe_float(node[1] if len(node) >= 2 else 0.0),
                            box=None,
                        )
                    )
                return

            for item in node:
                self._parse_legacy_node(item, lines)
            return

        if isinstance(node, list):
            for item in node:
                self._parse_legacy_node(item, lines)
            return

    def _score_lines(
        self,
        lines: List[OcrLine],
        image_size: Tuple[int, int],
    ) -> List[OcrLine]:
        scored: List[OcrLine] = []

        for line in lines:
            line.score = score_product_title_line(
                text=line.text,
                confidence=line.confidence,
                box=line.box,
                image_size=image_size,
            )
            scored.append(line)

        return sorted(scored, key=lambda item: item.score, reverse=True)

    def _build_candidates(self, lines: List[OcrLine], top_k: int) -> List[PackagedFoodCandidate]:
        all_ocr_text = " ".join(line.text for line in lines)

        title_lines = [
            line for line in lines
            if line.confidence >= self.min_text_confidence and line.score > 0.35
        ]

        if not title_lines:
            # 후보 점수가 낮아도 최상위 1개는 반환한다.
            title_lines = lines[:1]

        candidates: List[PackagedFoodCandidate] = []

        # 1차 후보: 상품명 가능성이 높은 line을 결합
        merged_source = self._select_merge_lines(title_lines)
        merged_text = self._build_display_text(merged_source)
        merged_conf = self._average_confidence(merged_source)

        if merged_text:
            candidates.append(
                PackagedFoodCandidate(
                    displayName=merged_text,
                    normalizedName=merged_text,
                    categorySuggestion=None,
                    confidence=merged_conf,
                    bbox=None,
                    ocrText=all_ocr_text,
                    ocrLines=[line.to_dict() for line in lines],
                    extractionReason="merged_product_title_lines",
                )
            )

        # 2차 후보: 개별 line 후보
        for line in title_lines:
            text = clean_ocr_text(line.text)
            if not text:
                continue

            if candidates and text == candidates[0].displayName:
                continue

            candidates.append(
                PackagedFoodCandidate(
                    displayName=text,
                    normalizedName=text,
                    categorySuggestion=None,
                    confidence=line.confidence,
                    bbox=line.box,
                    ocrText=line.text,
                    ocrLines=[line.to_dict()],
                    extractionReason="single_product_title_line",
                )
            )

            if len(candidates) >= top_k:
                break

        return candidates

    def _select_merge_lines(self, title_lines: List[OcrLine]) -> List[OcrLine]:
        """
        대표 후보 조립.
        - 점수 높은 line 중 노이즈가 아닌 것 위주로 최대 max_merge_lines개 사용.
        - 단, '서울우유'와 '우유'처럼 포함 관계가 있으면 중복 결합하지 않는다.
        """
        selected: List[OcrLine] = []

        for line in title_lines:
            text = clean_ocr_text(line.text)
            if not text:
                continue

            if is_noise_text(text):
                continue

            if any(text in existing.text or existing.text in text for existing in selected):
                # 포함 관계면 더 정보량이 큰 쪽 유지
                for idx, existing in enumerate(selected):
                    if existing.text in text and len(text) > len(existing.text):
                        selected[idx] = line
                continue

            selected.append(line)

            if len(selected) >= self.max_merge_lines:
                break

        if not selected and title_lines:
            selected = title_lines[:1]

        # 보기 좋게 원래 이미지상의 위→아래, 왼→오 순서로 정렬
        return sorted(selected, key=lambda line: box_sort_key(line.box))

    @staticmethod
    def _build_display_text(lines: List[OcrLine]) -> str:
        texts = [clean_ocr_text(line.text) for line in lines if clean_ocr_text(line.text)]
        return clean_ocr_text(" ".join(texts))

    @staticmethod
    def _average_confidence(lines: List[OcrLine]) -> float:
        if not lines:
            return 0.0
        return float(sum(line.confidence for line in lines) / len(lines))

    @staticmethod
    def _dedupe_lines(lines: List[OcrLine]) -> List[OcrLine]:
        deduped: List[OcrLine] = []
        seen = set()

        for line in lines:
            key = line.text
            if key in seen:
                continue
            seen.add(key)
            deduped.append(line)

        return deduped

    @staticmethod
    def _raw_to_debuggable(raw_result: Any) -> Any:
        if isinstance(raw_result, list):
            return [PackagedFoodOcr._raw_to_debuggable(item) for item in raw_result]

        if hasattr(raw_result, "json"):
            try:
                return raw_result.json
            except Exception:
                return str(raw_result)

        return to_jsonable(raw_result)

    @staticmethod
    def _safe_json_dumps(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError:
            return str(value)


_ocr_instance: Optional[PackagedFoodOcr] = None


def get_packaged_food_ocr() -> PackagedFoodOcr:
    global _ocr_instance

    if _ocr_instance is not None:
        return _ocr_instance

    lang = os.getenv("PACKAGED_FOOD_OCR_LANG", DEFAULT_OCR_LANG)
    min_confidence = float(os.getenv("PACKAGED_FOOD_OCR_MIN_CONFIDENCE", "0.30"))
    max_merge_lines = int(os.getenv("PACKAGED_FOOD_OCR_MAX_MERGE_LINES", "3"))
    debug = os.getenv("PACKAGED_FOOD_OCR_DEBUG", "false").lower() == "true"

    _ocr_instance = PackagedFoodOcr(
        lang=lang,
        min_text_confidence=min_confidence,
        max_merge_lines=max_merge_lines,
        debug=debug,
    )
    return _ocr_instance


def recognize_packaged_food_image(
    image_path: str | Path,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    ocr = get_packaged_food_ocr()
    return ocr.recognize(image_path=image_path, top_k=top_k)


def score_product_title_line(
    *,
    text: str,
    confidence: float,
    box: Optional[Any],
    image_size: Tuple[int, int],
) -> float:
    clean_text = clean_ocr_text(text)
    if not clean_text:
        return 0.0

    score = float(confidence)

    # 상품 키워드 가산
    if contains_product_keyword(clean_text):
        score += 0.65

    # 노이즈 문구 감점
    if is_noise_text(clean_text):
        score -= 0.75

    # 너무 긴 설명문은 감점
    length = len(clean_text)
    if 2 <= length <= 12:
        score += 0.15
    elif length > 18:
        score -= 0.30

    # 숫자/기호 비율이 높은 코드는 감점
    if digit_symbol_ratio(clean_text) > 0.55:
        score -= 0.45

    # 박스 크기/위치 가산
    box_info = box_metrics(box, image_size)
    if box_info:
        area_ratio, y_center_ratio = box_info

        # 상품명은 보통 글자가 크다.
        if area_ratio > 0.01:
            score += 0.20
        if area_ratio > 0.03:
            score += 0.35

        # 너무 아래쪽의 등급/영양 정보는 감점. 단 절대 규칙은 아니므로 약하게.
        if y_center_ratio > 0.72:
            score -= 0.20

    # 단독 일반명은 후보로는 유효하지만 브랜드명보다 낮게
    if clean_text in WEAK_SINGLE_WORDS:
        score -= 0.10

    return score


def contains_product_keyword(text: str) -> bool:
    return any(keyword in text for keyword in PRODUCT_KEYWORDS)


def is_noise_text(text: str) -> bool:
    clean_text = clean_ocr_text(text)
    return any(re.search(pattern, clean_text, flags=re.IGNORECASE) for pattern in NOISE_PATTERNS)


def digit_symbol_ratio(text: str) -> float:
    if not text:
        return 1.0
    digit_symbols = sum(1 for ch in text if not ch.isalpha() and not ("\uac00" <= ch <= "\ud7a3"))
    return digit_symbols / max(len(text), 1)


def box_metrics(box: Optional[Any], image_size: Tuple[int, int]) -> Optional[Tuple[float, float]]:
    if box is None:
        return None

    width, height = image_size
    if width <= 0 or height <= 0:
        return None

    try:
        # PaddleOCR 3.x rec_boxes는 [x1, y1, x2, y2]
        if isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
            x1, y1, x2, y2 = [float(v) for v in box]
        # polygon [[x,y], ...]
        elif isinstance(box, list) and len(box) >= 4 and isinstance(box[0], list):
            xs = [float(p[0]) for p in box if len(p) >= 2]
            ys = [float(p[1]) for p in box if len(p) >= 2]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
        else:
            return None

        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        area_ratio = area / float(width * height)
        y_center_ratio = ((y1 + y2) / 2.0) / float(height)

        return area_ratio, y_center_ratio
    except Exception:
        return None


def box_sort_key(box: Optional[Any]) -> Tuple[float, float]:
    if box is None:
        return (999999.0, 999999.0)

    try:
        if isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
            x1, y1, _, _ = [float(v) for v in box]
            return (y1, x1)

        if isinstance(box, list) and len(box) >= 4 and isinstance(box[0], list):
            xs = [float(p[0]) for p in box if len(p) >= 2]
            ys = [float(p[1]) for p in box if len(p) >= 2]
            return (min(ys), min(xs))
    except Exception:
        pass

    return (999999.0, 999999.0)


def clean_ocr_text(text: Any) -> str:
    text = str(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_jsonable(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]

    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            pass

    return str(value)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="packaged food OCR")
    parser.add_argument("--image", required=True, help="입력 이미지 경로")
    parser.add_argument("--topK", type=int, default=5)
    parser.add_argument("--lang", default=DEFAULT_OCR_LANG)
    parser.add_argument("--minConfidence", type=float, default=0.30)
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    ocr = PackagedFoodOcr(
        lang=args.lang,
        min_text_confidence=args.minConfidence,
        debug=args.debug,
    )
    result = ocr.recognize(args.image, top_k=args.topK)
    print(json.dumps(result, ensure_ascii=False, indent=2))
