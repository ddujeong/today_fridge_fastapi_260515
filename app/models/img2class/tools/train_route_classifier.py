"""
Train a YOLO classification route model with optional val/loss threshold stopping.

Example:
  python3 app/models/img2class/tools/train_route_classifier.py \
    --model yolov8n-cls.pt \
    --data app/models/img2class/ml_datasets/ingredient_route_dataset \
    --epochs 80 \
    --imgsz 224 \
    --batch 16 \
    --device mps \
    --project app/models/img2class/runs/classify \
    --name ingredient_route_v3_reg \
    --plots \
    --patience 12 \
    --dropout 0.2 \
    --weight-decay 0.0008 \
    --lr0 0.003 \
    --lrf 0.01 \
    --augment \
    --hsv-h 0.015 --hsv-s 0.5 --hsv-v 0.3 \
    --degrees 8 --translate 0.08 --scale 0.2 --fliplr 0.5 \
    --stop-val-loss 0.35

cd /Users/a0/Documents/git/project_final_backend_2

python3 app/models/img2class/tools/train_route_classifier.py \
  --model yolov8n-cls.pt \
  --data app/models/img2class/ml_datasets/ingredient_route_dataset \
  --epochs 80 \
  --imgsz 224 \
  --batch 16 \
  --device mps \
  --project /Users/a0/Documents/git/project_final_backend_2/app/models/img2class/runs/classify \
  --name ingredient_route_v3_reg_patience12 \
  --plots \
  --patience 8 \
  --dropout 0.2 \
  --weight-decay 0.0008 \
  --lr0 0.003 \
  --lrf 0.01 \
  --hsv-h 0.015 --hsv-s 0.5 --hsv-v 0.3 \
  --degrees 8 --translate 0.08 --scale 0.2 --fliplr 0.5 \
  --stop-val-loss 0.0035

  

"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any, Optional


def _last_val_loss_from_csv(save_dir: Path) -> Optional[float]:
    csv_path = save_dir / "results.csv"
    if not csv_path.exists():
        return None

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None

    last = rows[-1]
    raw = last.get("val/loss")
    if raw is None or str(raw).strip() == "":
        return None

    try:
        return float(raw)
    except ValueError:
        return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train ingredient route classifier (YOLO classify)")
    p.add_argument("--model", default="yolov8n-cls.pt")
    p.add_argument("--data", required=True)
    p.add_argument("--epochs", type=int, default=80)
    p.add_argument("--imgsz", type=int, default=224)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--device", default="mps")
    p.add_argument("--project", default="app/models/img2class/runs/classify")
    p.add_argument("--name", default="ingredient_route_v3_reg")
    p.add_argument("--plots", action="store_true")
    p.add_argument("--patience", type=int, default=12)
    p.add_argument("--dropout", type=float, default=0.2)
    p.add_argument("--weight-decay", type=float, default=0.0008)
    p.add_argument("--lr0", type=float, default=0.003)
    p.add_argument("--lrf", type=float, default=0.01)
    p.add_argument("--augment", action="store_true")
    p.add_argument("--hsv-h", type=float, default=0.015)
    p.add_argument("--hsv-s", type=float, default=0.5)
    p.add_argument("--hsv-v", type=float, default=0.3)
    p.add_argument("--degrees", type=float, default=8.0)
    p.add_argument("--translate", type=float, default=0.08)
    p.add_argument("--scale", type=float, default=0.2)
    p.add_argument("--fliplr", type=float, default=0.5)
    p.add_argument(
        "--stop-val-loss",
        type=float,
        default=None,
        help="Stop training early when val/loss <= this threshold.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError("ultralytics가 설치되어 있지 않습니다. pip install ultralytics") from exc

    model = YOLO(args.model)

    if args.stop_val_loss is not None:
        threshold_patience = max(1, int(args.patience))
        under_threshold_streak = 0

        def on_fit_epoch_end(trainer: Any) -> None:
            nonlocal under_threshold_streak
            save_dir = Path(str(getattr(trainer, "save_dir", ".")))
            val_loss = _last_val_loss_from_csv(save_dir)
            if val_loss is None:
                return
            if val_loss <= args.stop_val_loss:
                under_threshold_streak += 1
                print(
                    f"[EARLY-STOP CHECK] val/loss={val_loss:.6f} <= threshold={args.stop_val_loss:.6f} "
                    f"(streak={under_threshold_streak}/{threshold_patience})"
                )
                if under_threshold_streak >= threshold_patience:
                    trainer.stop = True
                    print(
                        f"[EARLY-STOP] val/loss <= threshold for {threshold_patience} consecutive epoch(s). "
                        "Stopping training."
                    )
            else:
                under_threshold_streak = 0

        model.add_callback("on_fit_epoch_end", on_fit_epoch_end)

    model.train(
        model=args.model,
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=args.project,
        name=args.name,
        plots=args.plots,
        patience=args.patience,
        dropout=args.dropout,
        weight_decay=args.weight_decay,
        lr0=args.lr0,
        lrf=args.lrf,
        augment=args.augment,
        hsv_h=args.hsv_h,
        hsv_s=args.hsv_s,
        hsv_v=args.hsv_v,
        degrees=args.degrees,
        translate=args.translate,
        scale=args.scale,
        fliplr=args.fliplr,
    )


if __name__ == "__main__":
    main()
