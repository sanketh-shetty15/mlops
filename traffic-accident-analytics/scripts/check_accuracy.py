"""
scripts/check_accuracy.py
--------------------------
Quick command to check the accuracy of the trained champion model.

Usage
-----
    python scripts/check_accuracy.py               # test set (Nov-Dec 2023)
    python scripts/check_accuracy.py --split val   # validation set (Sep-Oct)
    python scripts/check_accuracy.py --split train # training set (Jan-Aug)
    python scripts/check_accuracy.py --all         # all three splits
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def check_accuracy(split: str = "test", show_all: bool = False):
    import joblib
    import numpy as np
    from sklearn.metrics import accuracy_score
    from ml.feature_engineering import prepare_all
    from config.config import MODELS_DIR

    # ── Load model ─────────────────────────────────────────────────────────────
    model_path = MODELS_DIR / "best_model.pkl"
    if not model_path.exists():
        print("✗  No trained model found at models/best_model.pkl")
        print("   Run first: python ml/train.py")
        sys.exit(1)

    print("Loading model...")
    pipeline = joblib.load(str(model_path))

    # ── Load champion type ─────────────────────────────────────────────────────
    summary_path = MODELS_DIR / "training_summary.json"
    model_type = "unknown"
    if summary_path.exists():
        with open(summary_path) as f:
            summary = json.load(f)
        model_type = summary.get("champion_model", "unknown")

    # ── Load data ──────────────────────────────────────────────────────────────
    print("Loading data splits...")
    X_train, X_val, X_test, y_train, y_val, y_test, _ = prepare_all()

    splits = {
        "train": (X_train, y_train, "Jan–Aug 2023"),
        "val":   (X_val,   y_val,   "Sep–Oct 2023"),
        "test":  (X_test,  y_test,  "Nov–Dec 2023"),
    }

    targets = splits.keys() if show_all else [split]

    # ── Header ─────────────────────────────────────────────────────────────────
    print()
    print("=" * 50)
    print(f"  MODEL ACCURACY REPORT")
    print(f"  Champion model : {model_type.upper()}")
    print("=" * 50)

    for name in targets:
        X, y, period = splits[name]

        # XGBoost uses 0-indexed labels internally
        y_eval = y - 1 if model_type == "xgb" else y
        y_pred_raw = pipeline.predict(X)
        y_pred = y_pred_raw if model_type == "xgb" else y_pred_raw

        acc = accuracy_score(y_eval, y_pred)

        # Class-level breakdown
        label_map = {0: "Fatal", 1: "Serious", 2: "Slight"} if model_type == "xgb" \
               else {1: "Fatal", 2: "Serious", 3: "Slight"}
        class_acc = {}
        for code, label in label_map.items():
            mask = (y_eval == code)
            if mask.sum() > 0:
                class_acc[label] = accuracy_score(y_eval[mask], y_pred[mask])

        print(f"\n  Split     : {name.upper()}  ({period})")
        print(f"  Samples   : {len(X):,}")
        print(f"  Accuracy  : {acc * 100:.2f}%")
        print()
        print(f"  Per-class accuracy:")
        for label, a in class_acc.items():
            bar = "█" * int(a * 20)
            print(f"    {label:<8}  {a * 100:5.2f}%  {bar}")

    print()
    print("=" * 50)
    print("  TIP: High overall accuracy (~85%) is expected because")
    print("  85% of records are 'Slight'. Fatal accuracy matters most.")
    print("=" * 50)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check model accuracy")
    parser.add_argument(
        "--split",
        choices=["train", "val", "test"],
        default="test",
        help="Which data split to evaluate (default: test)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show accuracy for all three splits",
    )
    args = parser.parse_args()
    check_accuracy(split=args.split, show_all=args.all)
