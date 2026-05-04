"""
prepare_raw_ingredient_cls_dataset.py

GroceryStoreDataset에서 Fruit/Vegetables만 추출해
YOLO classification용 raw ingredient 세부 분류 데이터셋을 만든다.

사용:
    python app/models/ingredient/tools/prepare_raw_ingredient_cls_dataset.py \
      --source ./data_sources/GroceryStoreDataset/dataset \
      --out ./ml_datasets/raw_ingredient_cls_dataset \
      --mode copy

선택: --label-map-json (동기화·매핑 합의 후, 문서함 메모 참고)
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, Optional


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SPLITS = ("train", "val", "test")
RAW_GROUPS = ("Fruit", "Vegetables")


def normalize_map_key(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def load_label_map_normalized_names(label_map_json: Optional[Path]) -> Dict[str, str]:
    """소스 클래스 폴더명 -> 출력 normalizedName (없으면 원명 유지)."""
    if not label_map_json:
        return {}
    data = json.loads(label_map_json.read_text(encoding="utf-8"))
    raw = data.get("labels", {})
    out: Dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        nn = v.get("normalizedName") or v.get("normalized_name")
        if nn:
            out[normalize_map_key(str(k))] = str(nn)
    return out


def resolve_out_class_dir(source_class: str, remap: Dict[str, str]) -> str:
    key = normalize_map_key(source_class)
    return remap.get(key, source_class)


def copy_or_link(src: Path, dst: Path, mode: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        return

    if mode == "copy":
        shutil.copy2(src, dst)
    elif mode == "symlink":
        dst.symlink_to(src.resolve())
    else:
        raise ValueError(f"unknown mode: {mode}")


def build_dataset(source: Path, out: Path, mode: str, label_map_json: Optional[Path]) -> None:
    total = 0
    remap = load_label_map_normalized_names(label_map_json)

    for split in SPLITS:
        split_root = source / split

        if not split_root.exists():
            print(f"[skip] split not found: {split_root}")
            continue

        for group in RAW_GROUPS:
            group_root = split_root / group

            if not group_root.exists():
                print(f"[skip] group not found: {group_root}")
                continue

            for class_dir in sorted(group_root.iterdir()):
                if not class_dir.is_dir():
                    continue

                class_name = class_dir.name
                out_class = resolve_out_class_dir(class_name, remap)
                images = [
                    p for p in class_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
                ]

                for image in images:
                    dst = out / split / out_class / f"{class_name}__{image.name}"
                    copy_or_link(image, dst, mode)
                    total += 1

                suffix = f" -> {out_class}" if out_class != class_name else ""
                print(f"[{split}] {group}/{class_name}{suffix}: {len(images)} images")

    print()
    print(f"완료: {total} images")
    print(f"output: {out}")
    print()
    print("학습 예시:")
    print(f"yolo classify train model=yolov8n-cls.pt data={out} epochs=40 imgsz=224 batch=16 name=raw_ingredient_v1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="GroceryStoreDataset/dataset 경로")
    parser.add_argument("--out", required=True, help="출력 dataset 경로")
    parser.add_argument("--mode", choices=["copy", "symlink"], default="copy")
    parser.add_argument(
        "--label-map-json",
        type=Path,
        default=None,
        help="model_label_to_master.json 경로 (주면 출력 클래스 폴더를 normalizedName 으로 맞춤)",
    )
    args = parser.parse_args()

    build_dataset(
        source=Path(args.source),
        out=Path(args.out),
        mode=args.mode,
        label_map_json=args.label_map_json,
    )


if __name__ == "__main__":
    main()
