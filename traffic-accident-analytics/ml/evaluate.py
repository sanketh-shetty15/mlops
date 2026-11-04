"""
ml/evaluate.py
---------------
Evaluates trained models and selects the champion.

Metrics used
------------
macro-F1      — primary champion selection metric.
                Averages F1 equally across Fatal/Serious/Slight.
                Better than accuracy for imbalanced classes.

recall_fatal  — secondary champion selection metric (tie-break).
                "Of all real Fatal accidents, how many did we catch?"
                A false negative on Fatal (predicting Slight when it's
                Fatal) is the worst possible error.

confusion_matrix — saved as PNG to models/ and logged to MLflow.
                    Shows exactly where the model makes mistakes.

Champion selection rule
-----------------------
1. Filter out models below MIN_ACCEPTABLE_MACRO_F1
2. Pick the model with highest macro_f1
3. Tie-break: highest recall_fatal
"""

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # non-interactive backend — safe for servers
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    recall_score,
    roc_auc_score,
    precision_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    MODELS_DIR,
    ML_CLASS_NAMES,
    ML_CLASS_ORDER,
    MIN_ACCEPTABLE_MACRO_F1,
    MIN_ACCEPTABLE_FATAL_RECALL,
    get_logger,
)

logger = get_logger(__name__)


# ── Core evaluation ────────────────────────────────────────────────────────────

def evaluate_model(
    pipeline,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    model_type: str = "unknown",
    run_name: str = "model",
) -> dict:
    """
    Evaluate a fitted pipeline on the validation set.

    Parameters
    ----------
    pipeline   : fitted sklearn Pipeline (preprocessor + model)
    X_val      : validation features
    y_val      : validation labels (0-indexed for XGB, 1-indexed for RF/LGBM)
    model_type : "rf" | "xgb" | "lgbm" — affects label remapping
    run_name   : used for naming saved plots

    Returns
    -------
    dict of metrics: macro_f1, recall_fatal, recall_serious, recall_slight,
                     precision_fatal, roc_auc, accuracy
    """
    y_pred = pipeline.predict(X_val)
    y_prob = pipeline.predict_proba(X_val)

    # Normalise to 0-indexed labels for consistent metric calculation
    # XGBoost already returns 0-indexed; RF/LGBM return 1,2,3 → remap
    if model_type in ("rf", "lgbm"):
        # Labels are 1,2,3 → remap to 0,1,2
        y_val_idx  = y_val - 1
        y_pred_idx = y_pred - 1
    else:
        # XGBoost already 0-indexed
        y_val_idx  = y_val
        y_pred_idx = y_pred

    classes_present = sorted(np.unique(y_val_idx))

    # ── Per-class metrics ─────────────────────────────────────────────────────
    # classes: 0=Fatal, 1=Serious, 2=Slight (0-indexed)
    recall_per_class    = recall_score(
        y_val_idx, y_pred_idx, labels=classes_present,
        average=None, zero_division=0
    )
    precision_per_class = precision_score(
        y_val_idx, y_pred_idx, labels=classes_present,
        average=None, zero_division=0
    )

    # Map index back to class names
    idx_to_name = {0: "fatal", 1: "serious", 2: "slight"}
    recall_dict    = {idx_to_name[i]: float(recall_per_class[i])
                      for i in range(len(classes_present))}
    precision_dict = {idx_to_name[i]: float(precision_per_class[i])
                      for i in range(len(classes_present))}

    # ── Aggregate metrics ──────────────────────────────────────────────────────
    macro_f1 = float(f1_score(
        y_val_idx, y_pred_idx, average="macro", zero_division=0
    ))
    accuracy = float(np.mean(y_val_idx == y_pred_idx))

    # ROC-AUC (one-vs-rest)
    try:
        roc_auc = float(roc_auc_score(
            y_val_idx, y_prob,
            multi_class="ovr", average="macro",
            labels=classes_present,
        ))
    except Exception:
        roc_auc = 0.0

    metrics = {
        "macro_f1":         macro_f1,
        "accuracy":         accuracy,
        "roc_auc":          roc_auc,
        "recall_fatal":     recall_dict.get("fatal",   0.0),
        "recall_serious":   recall_dict.get("serious", 0.0),
        "recall_slight":    recall_dict.get("slight",  0.0),
        "precision_fatal":  precision_dict.get("fatal",   0.0),
        "precision_serious":precision_dict.get("serious", 0.0),
        "precision_slight": precision_dict.get("slight",  0.0),
    }

    # ── Full classification report ────────────────────────────────────────────
    class_labels = [ML_CLASS_NAMES[i + 1] for i in classes_present]
    report = classification_report(
        y_val_idx, y_pred_idx,
        target_names=class_labels,
        output_dict=True,
        zero_division=0,
    )
    metrics["classification_report"] = report

    # ── Confusion matrix ───────────────────────────────────────────────────────
    cm = confusion_matrix(y_val_idx, y_pred_idx, labels=classes_present)
    _save_confusion_matrix(cm, class_labels, model_type, run_name)

    # Log summary
    logger.info(
        "[%s] macro-F1=%.4f | acc=%.4f | roc_auc=%.4f"
        " | recall: Fatal=%.4f Serious=%.4f Slight=%.4f",
        run_name, macro_f1, accuracy, roc_auc,
        metrics["recall_fatal"],
        metrics["recall_serious"],
        metrics["recall_slight"],
    )

    # Warn if Fatal recall is below threshold
    if metrics["recall_fatal"] < MIN_ACCEPTABLE_FATAL_RECALL:
        logger.warning(
            "[%s] Fatal recall=%.4f is below threshold %.4f. "
            "Consider tuning class weights.",
            run_name, metrics["recall_fatal"], MIN_ACCEPTABLE_FATAL_RECALL,
        )

    return metrics


def _save_confusion_matrix(
    cm: np.ndarray,
    class_labels: list,
    model_type: str,
    run_name: str,
) -> Path:
    """Save confusion matrix as a PNG file."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = MODELS_DIR / f"confusion_matrix_{model_type}.png"

    fig, ax = plt.subplots(figsize=(7, 5))
    sns.heatmap(
        cm, annot=True, fmt="d",
        xticklabels=class_labels,
        yticklabels=class_labels,
        cmap="Blues",
        ax=ax,
        linewidths=0.5,
        linecolor="white",
    )
    ax.set_title(f"Confusion Matrix — {run_name}", fontsize=13, pad=12)
    ax.set_xlabel("Predicted", fontsize=11)
    ax.set_ylabel("Actual", fontsize=11)
    plt.tight_layout()
    plt.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Confusion matrix saved → %s", out_path)
    return out_path


# ── Champion selection ─────────────────────────────────────────────────────────

def select_champion(results: dict) -> tuple:
    """
    Select the best model from a dict of training results.

    Selection rule:
      1. Filter models below MIN_ACCEPTABLE_MACRO_F1
      2. Rank by macro_f1 (descending)
      3. Tie-break by recall_fatal (descending)

    Parameters
    ----------
    results : dict  {model_name: {"run_id": ..., "metrics": ..., "pipeline": ...}}

    Returns
    -------
    (champion_name, champion_info)
    """
    if not results:
        raise ValueError("No model results provided to select_champion()")

    # Build comparison DataFrame
    rows = []
    for name, info in results.items():
        m = info["metrics"]
        rows.append({
            "name":          name,
            "macro_f1":      m.get("macro_f1", 0),
            "recall_fatal":  m.get("recall_fatal", 0),
            "recall_serious":m.get("recall_serious", 0),
            "recall_slight": m.get("recall_slight", 0),
            "roc_auc":       m.get("roc_auc", 0),
        })

    df = pd.DataFrame(rows)
    logger.info("Model comparison:\n%s", df.to_string(index=False))

    # Filter below minimum threshold
    eligible = df[df["macro_f1"] >= MIN_ACCEPTABLE_MACRO_F1].copy()
    if eligible.empty:
        logger.warning(
            "No model meets the minimum macro-F1 threshold (%.2f). "
            "Using best available.",
            MIN_ACCEPTABLE_MACRO_F1
        )
        eligible = df.copy()

    # Sort: macro_f1 descending, then recall_fatal descending
    eligible.sort_values(
        ["macro_f1", "recall_fatal"],
        ascending=[False, False],
        inplace=True,
    )

    champion_name = eligible.iloc[0]["name"]
    champion_info = results[champion_name]

    logger.info(
        "Champion selected: %s  (macro-F1=%.4f, recall_fatal=%.4f)",
        champion_name,
        eligible.iloc[0]["macro_f1"],
        eligible.iloc[0]["recall_fatal"],
    )

    # Save comparison to disk
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(MODELS_DIR / "model_comparison.csv", index=False)
    logger.info("Model comparison saved → %s", MODELS_DIR / "model_comparison.csv")

    return champion_name, champion_info


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick smoke test — load saved model and evaluate on test set
    import joblib
    from ml.feature_engineering import prepare_all

    logger.info("Loading saved champion model for test-set evaluation...")
    pipeline = joblib.load(str(MODELS_DIR / "best_model.pkl"))

    (_, _, X_test, _, _, y_test, _) = prepare_all()

    # Detect model type from saved summary
    summary_path = MODELS_DIR / "training_summary.json"
    model_type = "rf"
    if summary_path.exists():
        with open(summary_path) as f:
            summary = json.load(f)
        model_type = summary.get("champion_model", "rf")

    metrics = evaluate_model(pipeline, X_test, y_test,
                             model_type=model_type, run_name="test_eval")
    print(f"\nTest set evaluation:")
    print(f"  macro-F1      : {metrics['macro_f1']:.4f}")
    print(f"  recall_fatal  : {metrics['recall_fatal']:.4f}")
    print(f"  recall_serious: {metrics['recall_serious']:.4f}")
    print(f"  roc_auc       : {metrics['roc_auc']:.4f}")
