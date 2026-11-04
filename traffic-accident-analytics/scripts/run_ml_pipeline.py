"""
scripts/run_ml_pipeline.py
----------------------------
End-to-end Part 2 ML pipeline runner — no Airflow required.

Runs the same stages as ml_training_pipeline.py DAG but directly
from the command line. Use this for development and on Windows where
Airflow is not installed.

Usage
-----
    # Full ML pipeline (train all 3 models)
    python scripts/run_ml_pipeline.py

    # Train one model only
    python scripts/run_ml_pipeline.py --model rf
    python scripts/run_ml_pipeline.py --model xgb
    python scripts/run_ml_pipeline.py --model lgbm

    # Skip model registration (no MLflow registry needed)
    python scripts/run_ml_pipeline.py --skip-registry

    # Skip monitoring checks
    python scripts/run_ml_pipeline.py --skip-monitoring

    # Start from a specific stage
    python scripts/run_ml_pipeline.py --start-from train
    python scripts/run_ml_pipeline.py --start-from monitoring

Stages
------
1. prepare_features      Build X/y from accidents_with_weather.csv
2. train                 RF + XGBoost + LightGBM with MLflow tracking
3. register              MLflow Model Registry promotion
4. monitoring            Drift detection + performance evaluation
"""

import sys
import time
import argparse
import traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import MODELS_DIR, get_logger

logger = get_logger("run_ml_pipeline")

STAGE_ORDER = ["features", "train", "register", "monitoring"]


# ── Helper ─────────────────────────────────────────────────────────────────────

def _header(msg: str) -> None:
    sep = "=" * 60
    logger.info("\n%s\n  %s\n%s", sep, msg, sep)


def _step(name: str, fn, *args, **kwargs):
    logger.info("▶  Starting: %s", name)
    t0 = time.time()
    try:
        result = fn(*args, **kwargs)
        logger.info("✓  Completed: %s (%.1fs)", name, time.time() - t0)
        return result
    except Exception as exc:
        logger.error("✗  FAILED: %s (%.1fs)", name, time.time() - t0)
        logger.error("   %s", exc)
        logger.debug(traceback.format_exc())
        raise


# ── Stage functions ────────────────────────────────────────────────────────────

def stage_features():
    _header("STAGE 1: FEATURE ENGINEERING")
    from ml.feature_engineering import prepare_all

    (X_train, X_val, X_test,
     y_train, y_val, y_test,
     preprocessor) = _step("Prepare features", prepare_all)

    logger.info(
        "Split: train=%d  val=%d  test=%d",
        len(X_train), len(X_val), len(X_test)
    )
    return X_train, X_val, X_test, y_train, y_val, y_test, preprocessor


def stage_train(models_to_train: list):
    _header("STAGE 2: MODEL TRAINING")
    from ml.train import train_all_models

    result = _step(
        f"Train {models_to_train}",
        train_all_models,
        models_to_train=models_to_train,
    )

    champion  = result["champion_name"]
    metrics   = result["champion_metrics"]
    run_id    = result["champion_run_id"]

    logger.info("=" * 60)
    logger.info("  CHAMPION: %s", champion.upper())
    logger.info("  macro-F1      : %.4f", metrics.get("macro_f1", 0))
    logger.info("  recall_fatal  : %.4f", metrics.get("recall_fatal", 0))
    logger.info("  recall_serious: %.4f", metrics.get("recall_serious", 0))
    logger.info("  roc_auc       : %.4f", metrics.get("roc_auc", 0))
    logger.info("  MLflow run_id : %s",  run_id)
    logger.info("=" * 60)

    return result


def stage_register(result: dict):
    _header("STAGE 3: MODEL REGISTRY")
    from ml.register_model import register_champion

    champion_name = result["champion_name"]
    champion_run  = result["champion_run_id"]
    metrics       = result["champion_metrics"]

    version = _step(
        "Register champion in MLflow",
        register_champion,
        run_id     = champion_run,
        model_name = champion_name,
        metrics    = {
            "macro_f1":     metrics.get("macro_f1", 0),
            "recall_fatal": metrics.get("recall_fatal", 0),
        },
    )
    logger.info(
        "Model registered as version %s in stage: %s",
        version,
        "Production" if metrics.get("macro_f1", 0) >= 0.30 else "Staging"
    )
    return version


def stage_monitoring():
    _header("STAGE 4: MONITORING")
    from monitoring.performance_monitor import run_full_monitoring

    report = _step("Run full monitoring suite", run_full_monitoring)

    p = report.get("performance", {})
    logger.info("Monitoring results:")
    logger.info("  macro-F1      : %.4f", p.get("macro_f1", 0))
    logger.info("  recall_fatal  : %.4f", p.get("recall_fatal", 0))
    logger.info("  fn_rate_fatal : %.4f", p.get("fn_rate_fatal", 0))
    logger.info("  Feature drift : %s",
                report.get("feature_drift",  {}).get("retrain_required", False))
    logger.info("  Location drift: %s",
                report.get("location_drift", {}).get("retrain_required", False))
    logger.info("  Retrain needed: %s", report.get("retrain_required", False))

    return report


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run Part 2 ML pipeline end-to-end"
    )
    parser.add_argument(
        "--model",
        choices=["rf", "xgb", "lgbm", "all"],
        default="all",
        help="Which model(s) to train (default: all)",
    )
    parser.add_argument(
        "--skip-registry",
        action="store_true",
        help="Skip MLflow model registry step",
    )
    parser.add_argument(
        "--skip-monitoring",
        action="store_true",
        help="Skip monitoring checks",
    )
    parser.add_argument(
        "--start-from",
        choices=STAGE_ORDER,
        default="features",
        help="Start from this stage (assumes prior stages already done)",
    )
    args = parser.parse_args()

    models = ["rf", "xgb", "lgbm"] if args.model == "all" else [args.model]
    start_idx = STAGE_ORDER.index(args.start_from)

    t_start = time.time()
    logger.info("=" * 60)
    logger.info("  PART 2 — ML TRAINING PIPELINE")
    logger.info("  Started : %s", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
    logger.info("  Models  : %s", models)
    logger.info("  Start   : %s", args.start_from)
    logger.info("=" * 60)

    result = None

    try:
        # Stage 1 — features
        if start_idx <= STAGE_ORDER.index("features"):
            stage_features()

        # Stage 2 — train
        if start_idx <= STAGE_ORDER.index("train"):
            result = stage_train(models)

        # Stage 3 — register
        if not args.skip_registry:
            if start_idx <= STAGE_ORDER.index("register"):
                if result is None:
                    # Load champion info from saved summary
                    import json
                    summary_path = MODELS_DIR / "training_summary.json"
                    if summary_path.exists():
                        with open(summary_path) as f:
                            summary = json.load(f)
                        # Build a minimal result dict
                        result = {
                            "champion_name":    summary.get("champion_model", ""),
                            "champion_run_id":  summary.get("champion_run_id", ""),
                            "champion_metrics": summary.get("metrics", {}),
                        }
                    else:
                        logger.warning(
                            "No training summary found. Skipping registry."
                        )
                if result and result.get("champion_run_id"):
                    stage_register(result)
        else:
            logger.info("⏭  Skipping registry (--skip-registry)")

        # Stage 4 — monitoring
        if not args.skip_monitoring:
            if start_idx <= STAGE_ORDER.index("monitoring"):
                stage_monitoring()
        else:
            logger.info("⏭  Skipping monitoring (--skip-monitoring)")

    except Exception as exc:
        elapsed = time.time() - t_start
        logger.error("\n" + "=" * 60)
        logger.error("  ML PIPELINE FAILED after %.1fs", elapsed)
        logger.error("  Error: %s", exc)
        logger.error("=" * 60)
        sys.exit(1)

    elapsed = time.time() - t_start
    logger.info("\n" + "=" * 60)
    logger.info("  ML PIPELINE COMPLETE in %.1fs", elapsed)
    logger.info("  Saved model: %s", MODELS_DIR / "best_model.pkl")
    logger.info("  MLflow UI  : mlflow ui --backend-store-uri %s",
                "sqlite:///mlflow/mlflow.db")
    logger.info("  Start API  : uvicorn api.main:app --port 8000")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
