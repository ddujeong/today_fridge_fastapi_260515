"""
prepare_raw_ingredient_cls_dataset.py

GroceryStoreDataset에서 Fruit/Vegetables만 추출해
YOLO classification용 raw ingredient 세부 분류 데이터셋을 만든다.

사용:
    python app/models/ingredient/tools/prepare_raw_ingredient_cls_dataset.py \
      --source ./data_sources/GroceryStoreDataset/dataset \
      --out ./ml_datasets/raw_ingredient_cls_dataset \
      --mode copy
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SPLITS = ("train", "val", "test")
RAW_GROUPS = ("Fruit", "Vegetables")


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


def build_dataset(source: Path, out: Path, mode: str) -> None:
    total = 0

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
                images = [
                    p for p in class_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
                ]

                for image in images:
                    dst = out / split / class_name / f"{class_name}__{image.name}"
                    copy_or_link(image, dst, mode)
                    total += 1

                print(f"[{split}] {group}/{class_name}: {len(images)} images")

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
    args = parser.parse_args()

    build_dataset(source=Path(args.source), out=Path(args.out), mode=args.mode)


if __name__ == "__main__":
    main()
