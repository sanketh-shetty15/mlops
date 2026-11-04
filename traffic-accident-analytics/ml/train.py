

import sys
import json
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

warnings.filterwarnings("ignore", category=UserWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    MODELS_DIR,
    MLFLOW_TRACKING_URI,
    MLFLOW_EXPERIMENT_NAME,
    ML_FEATURE_COLUMNS,
    ML_CLASS_NAMES,
    RF_PARAMS,
    XGB_PARAMS,
    LGBM_PARAMS,
    get_logger,
)
from ml.feature_engineering import prepare_all
from ml.evaluate import evaluate_model, select_champion

logger = get_logger(__name__)

# ── MLflow setup ───────────────────────────────────────────────────────────────

def setup_mlflow():
    """Configure MLflow tracking URI and create experiment if needed."""
    from pathlib import Path
    # Ensure mlflow directory exists
    mlflow_dir = Path(MLFLOW_TRACKING_URI.replace("sqlite:///", "")).parent
    mlflow_dir.mkdir(parents=True, exist_ok=True)

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    experiment = mlflow.get_experiment_by_name(MLFLOW_EXPERIMENT_NAME)
    if experiment is None:
        mlflow.create_experiment(MLFLOW_EXPERIMENT_NAME)
        logger.info("Created MLflow experiment: %s", MLFLOW_EXPERIMENT_NAME)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
    logger.info("MLflow tracking URI: %s", MLFLOW_TRACKING_URI)
    logger.info("MLflow experiment : %s", MLFLOW_EXPERIMENT_NAME)


# ── Model builders ─────────────────────────────────────────────────────────────

def _build_rf_pipeline(preprocessor) -> Pipeline:
    """Random Forest with balanced class weights."""
    model = RandomForestClassifier(**RF_PARAMS)
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def _build_xgb_pipeline(preprocessor, y_train) -> Pipeline:
    """
    XGBoost with sample weights for class imbalance handling.
    XGBoost does not support class_weight — sample_weight is passed at fit().
    Labels must be 0-indexed (1→0, 2→1, 3→2) — handled in _fit_and_log.
    """
    params = {k: v for k, v in XGB_PARAMS.items()
              if k not in ("use_label_encoder", "num_class", "objective")}
    # XGBClassifier auto-detects multiclass from the data
    model = XGBClassifier(**params)
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def _build_lgbm_pipeline(preprocessor) -> Pipeline:
    """LightGBM with balanced class weights."""
    model = LGBMClassifier(**LGBM_PARAMS)
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


# ── Training functions ─────────────────────────────────────────────────────────

def _fit_and_log(
    run_name: str,
    pipeline: Pipeline,
    model_params: dict,
    model_type: str,
    X_train, y_train,
    X_val, y_val,
    sample_weight=None,
) -> tuple:
    """
    Fit a pipeline, evaluate on validation set, log everything to MLflow.

    Returns (run_id, val_metrics_dict)
    """
    logger.info("Training: %s ...", run_name)

    with mlflow.start_run(run_name=run_name) as run:
        run_id = run.info.run_id

        # ── Log parameters ────────────────────────────────────────────────────
        mlflow.log_param("model_type",    model_type)
        mlflow.log_param("train_samples", len(X_train))
        mlflow.log_param("val_samples",   len(X_val))
        mlflow.log_param("features",      len(ML_FEATURE_COLUMNS))
        mlflow.log_param("train_months",  "Jan-Aug 2023")
        mlflow.log_param("val_months",    "Sep-Oct 2023")
        for k, v in model_params.items():
            mlflow.log_param(k, v)

        # ── Fit ───────────────────────────────────────────────────────────────
        # XGBoost requires 0-indexed labels (1→0, 2→1, 3→2)
        # RF and LightGBM accept 1,2,3 directly (class_weight="balanced")
        is_xgb = (model_type == "xgb")

        if is_xgb:
            y_train_fit = y_train - 1   # remap: 1→0, 2→1, 3→2
            y_val_eval  = y_val   - 1
        else:
            y_train_fit = y_train       # keep 1, 2, 3
            y_val_eval  = y_val

        # Sample weights for class balancing
        # XGBoost needs explicit sample_weight (no class_weight param)
        # RF and LGBM use class_weight="balanced" internally
        sw = compute_sample_weight("balanced", y_train_fit)

        fit_params = {}
        if is_xgb:
            fit_params["model__sample_weight"] = sw

        pipeline.fit(X_train, y_train_fit, **fit_params)

        # ── Evaluate on validation set ────────────────────────────────────────
        metrics = evaluate_model(
            pipeline, X_val, y_val_eval,
            model_type=model_type,
            run_name=run_name,
        )

        # ── Log metrics to MLflow ─────────────────────────────────────────────
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, (int, float)):
                mlflow.log_metric(metric_name, metric_value)

        # ── Log confusion matrix artifact ─────────────────────────────────────
        cm_path = MODELS_DIR / f"confusion_matrix_{model_type}.png"
        if cm_path.exists():
            mlflow.log_artifact(str(cm_path))

        # ── Log classification report artifact ────────────────────────────────
        report_path = MODELS_DIR / f"classification_report_{model_type}.json"
        with open(report_path, "w") as f:
            json.dump(metrics, f, indent=2)
        mlflow.log_artifact(str(report_path))

        # ── Log the fitted pipeline as a model artifact ───────────────────────
        # MLflow 3.x uses skops serialization with security checks.
        # We auto-detect all untrusted types and trust them since we
        # built the model ourselves from known-clean data.
        import tempfile
        import os as _os
        import skops.io as sio

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = _os.path.join(tmp, "model.skops")
            sio.dump(pipeline, tmp_path)
            trusted_types = list(sio.get_untrusted_types(file=tmp_path))

        try:
            mlflow.sklearn.log_model(
                pipeline,
                name="model",
                registered_model_name=None,
                skops_trusted_types=trusted_types,
            )
        except TypeError:
            # Fallback for MLflow versions without skops_trusted_types param
            mlflow.sklearn.log_model(
                pipeline,
                artifact_path="model",
                registered_model_name=None,
            )

        logger.info(
            "%s  |  macro-F1=%.4f  recall_fatal=%.4f  recall_serious=%.4f",
            run_name,
            metrics.get("macro_f1", 0),
            metrics.get("recall_fatal", 0),
            metrics.get("recall_serious", 0),
        )

    return run_id, metrics, pipeline


# ── Main training orchestrator ────────────────────────────────────────────────

def train_all_models(models_to_train: list = None) -> dict:
    """
    Train all requested models, evaluate on validation set,
    select the champion, and save it to disk.

    Parameters
    ----------
    models_to_train : list of str, optional
        Subset of ["rf", "xgb", "lgbm"]. If None, trains all three.

    Returns
    -------
    dict with keys: results, champion_name, champion_run_id,
                    champion_pipeline, champion_metrics
    """
    if models_to_train is None:
        models_to_train = ["rf", "xgb", "lgbm"]

    setup_mlflow()

    logger.info("=" * 60)
    logger.info("  ML TRAINING PIPELINE — PART 2")
    logger.info("  Models: %s", models_to_train)
    logger.info("=" * 60)

    # ── Prepare data ──────────────────────────────────────────────────────────
    (X_train, X_val, X_test,
     y_train, y_val, y_test,
     preprocessor) = prepare_all()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    # ── Random Forest ─────────────────────────────────────────────────────────
    if "rf" in models_to_train:
        pipeline = _build_rf_pipeline(preprocessor)
        run_id, metrics, fitted = _fit_and_log(
            run_name    = "random_forest",
            pipeline    = pipeline,
            model_params= RF_PARAMS,
            model_type  = "rf",
            X_train=X_train, y_train=y_train,
            X_val=X_val,     y_val=y_val,
        )
        results["rf"] = {
            "run_id": run_id, "metrics": metrics, "pipeline": fitted
        }

    # ── XGBoost ───────────────────────────────────────────────────────────────
    if "xgb" in models_to_train:
        pipeline = _build_xgb_pipeline(preprocessor, y_train)
        run_id, metrics, fitted = _fit_and_log(
            run_name    = "xgboost",
            pipeline    = pipeline,
            model_params= XGB_PARAMS,
            model_type  = "xgb",
            X_train=X_train, y_train=y_train,
            X_val=X_val,     y_val=y_val,
        )
        results["xgb"] = {
            "run_id": run_id, "metrics": metrics, "pipeline": fitted
        }
    if "lgbm" in models_to_train:
        pipeline = _build_lgbm_pipeline(preprocessor)
        run_id, metrics, fitted = _fit_and_log(
            run_name    = "lightgbm",
            pipeline    = pipeline,
            model_params= LGBM_PARAMS,
            model_type  = "lgbm",
            X_train=X_train, y_train=y_train,
            X_val=X_val,     y_val=y_val,
        )
        results["lgbm"] = {
            "run_id": run_id, "metrics": metrics, "pipeline": fitted
        }

    # ── Select champion ───────────────────────────────────────────────────────
    champion_name, champion_info = select_champion(results)
    champion_pipeline = champion_info["pipeline"]
    champion_metrics  = champion_info["metrics"]
    champion_run_id   = champion_info["run_id"]

    logger.info("=" * 60)
    logger.info("  CHAMPION MODEL: %s", champion_name.upper())
    logger.info("  macro-F1       : %.4f", champion_metrics.get("macro_f1", 0))
    logger.info("  recall_fatal   : %.4f", champion_metrics.get("recall_fatal", 0))
    logger.info("  recall_serious : %.4f", champion_metrics.get("recall_serious", 0))
    logger.info("  MLflow run_id  : %s",  champion_run_id)
    logger.info("=" * 60)

    # ── Save champion to disk ─────────────────────────────────────────────────
    joblib.dump(champion_pipeline, str(MODELS_DIR / "best_model.pkl"))
    logger.info("Champion saved → %s", MODELS_DIR / "best_model.pkl")

    # Save preprocessor separately (used by monitoring)
    preprocessor_fitted = champion_pipeline.named_steps["preprocessor"]
    joblib.dump(preprocessor_fitted, str(MODELS_DIR / "preprocessor.pkl"))
    logger.info("Preprocessor saved → %s", MODELS_DIR / "preprocessor.pkl")

    # Save champion summary
    summary = {
        "champion_model":  champion_name,
        "champion_run_id": champion_run_id,
        "metrics":         {k: v for k, v in champion_metrics.items()
                            if isinstance(v, (int, float))},
        "all_results": {
            name: {k: v for k, v in info["metrics"].items()
                   if isinstance(v, (int, float))}
            for name, info in results.items()
        },
    }
    summary_path = MODELS_DIR / "training_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Training summary → %s", summary_path)

    return {
        "results":           results,
        "champion_name":     champion_name,
        "champion_run_id":   champion_run_id,
        "champion_pipeline": champion_pipeline,
        "champion_metrics":  champion_metrics,
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train severity prediction models")
    parser.add_argument(
        "--model", choices=["rf", "xgb", "lgbm", "all"], default="all",
        help="Which model to train (default: all)"
    )
    args = parser.parse_args()
    models = ["rf", "xgb", "lgbm"] if args.model == "all" else [args.model]
    train_all_models(models_to_train=models)
