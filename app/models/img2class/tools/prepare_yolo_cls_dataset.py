"""
prepare_yolo_cls_dataset.py

공개 이미지 데이터셋을 YOLO classification용 라우팅 데이터셋으로 재구성하는 스크립트.

목표 폴더 구조:
    ingredient_route_dataset/
      train/
        raw_ingredient/
        packaged_food/
        other/
      val/
        raw_ingredient/
        packaged_food/
        other/
      test/
        raw_ingredient/
        packaged_food/
        other/

사용 예시:
    python prepare_yolo_cls_dataset.py \
      --source ./data_sources/GroceryStoreDataset \
      --mapping ./mapping_grocery_template.json \
      --out ./ingredient_route_dataset \
      --split 0.7 0.2 0.1 \
      --mode copy

주의:
- 이 스크립트는 source 내부의 폴더명을 class명으로 보고 mapping한다.
- dataset마다 폴더 구조가 다를 수 있으므로 먼저 아래 명령으로 구조를 확인한다.
    find ./data_sources/GroceryStoreDataset -maxdepth 4 -type d
- 매핑되지 않은 class 폴더는 건너뛴다.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def normalize_name(name: str) -> str:
    return (
        name.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def load_mapping(path: Path) -> Dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    mapping = {}
    for source_class, target_class in raw.items():
        mapping[normalize_name(source_class)] = normalize_name(target_class)
    return mapping


def find_image_files(source_root: Path) -> List[Path]:
    return [
        path for path in source_root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]


def infer_source_class(image_path: Path, source_root: Path, mapping: Dict[str, str]) -> str | None:
    """
    이미지 경로의 부모 폴더들 중 mapping에 존재하는 폴더명을 source class로 본다.

    예:
        source/class_name/img.jpg
        source/train/class_name/img.jpg
        source/Fruits/Apple/img.jpg

    위처럼 dataset마다 구조가 달라도 class 폴더명이 mapping에 있으면 잡힌다.
    """
    try:
        relative = image_path.relative_to(source_root)
    except ValueError:
        return None

    # 파일명 제외 경로 요소를 뒤에서부터 검사한다.
    parts = list(relative.parts[:-1])
    for part in reversed(parts):
        normalized = normalize_name(part)
        if normalized in mapping:
            return normalized
    return None


def split_items_by_group(items: List[Path], split: Tuple[float, float, float], seed: int) -> Dict[str, List[Path]]:
    """
    이미지들을 부모 폴더명(제품명) 기준으로 그룹화하여 train/val/test로 분할한다.
    동일 제품의 사진이 여러 세트에 섞이는 것을 방지한다.
    """
    groups: Dict[str, List[Path]] = {}
    for path in items:
        # GroceryStoreDataset 구조상 부모 폴더명이 제품명임
        product_name = path.parent.name
        groups.setdefault(product_name, []).append(path)
    
    group_names = sorted(groups.keys())
    rng = random.Random(seed)
    rng.shuffle(group_names)
    
    n = len(group_names)
    train_ratio, val_ratio, _ = split
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    
    train_groups = set(group_names[:n_train])
    val_groups = set(group_names[n_train:n_train + n_val])
    
    result = {"train": [], "val": [], "test": []}
    for group_name, paths in groups.items():
        if group_name in train_groups:
            result["train"].extend(paths)
        elif group_name in val_groups:
            result["val"].extend(paths)
        else:
            result["test"].extend(paths)
    return result


def safe_copy_or_link(src: Path, dst: Path, mode: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        return

    if mode == "copy":
        shutil.copy2(src, dst)
    elif mode == "symlink":
        dst.symlink_to(src.resolve())
    else:
        raise ValueError(f"지원하지 않는 mode입니다: {mode}")


def build_dataset(
    source_root: Path,
    mapping_path: Path,
    out_root: Path,
    split: Tuple[float, float, float],
    seed: int,
    mode: str,
) -> None:
    mapping = load_mapping(mapping_path)

    target_classes = sorted(set(mapping.values()))
    # 기존 데이터가 있으면 삭제하여 꼬이지 않게 함
    if out_root.exists():
        print(f"Cleaning existing directory: {out_root}")
        shutil.rmtree(out_root)

    for split_name in ["train", "val", "test"]:
        for target_class in target_classes:
            (out_root / split_name / target_class).mkdir(parents=True, exist_ok=True)

    images = find_image_files(source_root)

    grouped: Dict[str, List[Path]] = {}
    skipped = 0

    for image_path in images:
        source_class = infer_source_class(image_path, source_root, mapping)
        if source_class is None:
            skipped += 1
            continue

        target_class = mapping[source_class]
        grouped.setdefault(target_class, []).append(image_path)

    print("=== Source summary ===")
    print(f"source_root: {source_root}")
    print(f"total images found: {len(images)}")
    print(f"mapped images: {sum(len(v) for v in grouped.values())}")
    print(f"skipped images: {skipped}")
    print()

    for target_class, class_images in sorted(grouped.items()):
        # 제품 단위 분할 적용
        split_map = split_items_by_group(class_images, split, seed)
        print(f"[{target_class}]")

        for split_name, split_images in split_map.items():
            print(f"  {split_name}: {len(split_images)} images")

            for src in split_images:
                class_hint = src.parent.name
                dst_name = f"{normalize_name(class_hint)}__{src.stem}{src.suffix.lower()}"
                dst = out_root / split_name / target_class / dst_name
                safe_copy_or_link(src, dst, mode=mode)

    print()
    print("완료.")
    print(f"YOLO classification data path: {out_root}")
    print()
    print("학습 예시:")
    print(f"yolo classify train model=yolov8n-cls.pt data={out_root} epochs=30 imgsz=224")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="원본 데이터셋 루트 폴더")
    parser.add_argument("--mapping", required=True, help="source class → target class 매핑 JSON")
    parser.add_argument("--out", required=True, help="출력 YOLO classification dataset 폴더")
    parser.add_argument("--split", nargs=3, type=float, default=[0.7, 0.2, 0.1], help="train val test 비율")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mode", choices=["copy", "symlink"], default="copy")
    args = parser.parse_args()

    build_dataset(
        source_root=Path(args.source),
        mapping_path=Path(args.mapping),
        out_root=Path(args.out),
        split=(args.split[0], args.split[1], args.split[2]),
        seed=args.seed,
        mode=args.mode,
    )


if __name__ == "__main__":
    main()
