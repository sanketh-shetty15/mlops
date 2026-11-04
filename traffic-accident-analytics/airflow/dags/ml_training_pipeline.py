"""
airflow/dags/ml_training_pipeline.py
--------------------------------------
Apache Airflow DAG for the Part 2 MLOps training pipeline.

This DAG runs AFTER the Part 1 data pipeline has completed and the
accident_analytics_mart table is populated.

DAG structure
-------------
start
  ↓
prepare_features
  ↓
train_random_forest ──┐
train_xgboost        ──┼── (parallel)
train_lightgbm       ──┘
  ↓
evaluate_and_select_champion
  ↓
register_model_to_mlflow
  ↓
run_monitoring_checks
  ↓
ml_pipeline_complete

Schedule: None (manually triggered)
  - Trigger manually after new STATS19 data is published
  - Or after run_monitoring_checks detects retraining is required

Dependencies: Part 1 DAG (traffic_accident_pipeline) must have
              completed successfully first.
"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator

# ── Default task arguments ─────────────────────────────────────────────────────
default_args = {
    "owner":            "traffic_analytics_ml",
    "depends_on_past":  False,
    "start_date":       datetime(2024, 1, 1),
    "email_on_failure": False,
    "email_on_retry":   False,
    "retries":          1,
    "retry_delay":      timedelta(minutes=10),
}


# ── Task callables ─────────────────────────────────────────────────────────────

def task_prepare_features(**context):
    """
    Load accidents_with_weather.csv, build feature matrix X and target y.
    Apply chronological split: train=Jan-Aug, val=Sep-Oct, test=Nov-Dec.
    Save feature_names.json to models/.
    """
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: prepare_features ===")

    from ml.feature_engineering import prepare_all
    (X_train, X_val, X_test,
     y_train, y_val, y_test,
     preprocessor) = prepare_all()

    logger.info(
        "Features prepared: train=%d  val=%d  test=%d",
        len(X_train), len(X_val), len(X_test)
    )
    context["ti"].xcom_push(key="train_rows", value=int(len(X_train)))
    context["ti"].xcom_push(key="val_rows",   value=int(len(X_val)))
    context["ti"].xcom_push(key="test_rows",  value=int(len(X_test)))


def task_train_random_forest(**context):
    """Train Random Forest with class_weight=balanced. Log to MLflow."""
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: train_random_forest ===")

    from ml.train import train_all_models
    result = train_all_models(models_to_train=["rf"])

    rf_metrics = result["results"].get("rf", {}).get("metrics", {})
    run_id     = result["results"].get("rf", {}).get("run_id", "")

    logger.info(
        "RF complete: macro-F1=%.4f  recall_fatal=%.4f",
        rf_metrics.get("macro_f1", 0),
        rf_metrics.get("recall_fatal", 0),
    )
    context["ti"].xcom_push(key="rf_run_id",      value=run_id)
    context["ti"].xcom_push(key="rf_macro_f1",    value=rf_metrics.get("macro_f1", 0))
    context["ti"].xcom_push(key="rf_recall_fatal",value=rf_metrics.get("recall_fatal", 0))


def task_train_xgboost(**context):
    """Train XGBoost with sample weights for class imbalance. Log to MLflow."""
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: train_xgboost ===")

    from ml.train import train_all_models
    result = train_all_models(models_to_train=["xgb"])

    xgb_metrics = result["results"].get("xgb", {}).get("metrics", {})
    run_id      = result["results"].get("xgb", {}).get("run_id", "")

    logger.info(
        "XGB complete: macro-F1=%.4f  recall_fatal=%.4f",
        xgb_metrics.get("macro_f1", 0),
        xgb_metrics.get("recall_fatal", 0),
    )
    context["ti"].xcom_push(key="xgb_run_id",      value=run_id)
    context["ti"].xcom_push(key="xgb_macro_f1",    value=xgb_metrics.get("macro_f1", 0))
    context["ti"].xcom_push(key="xgb_recall_fatal",value=xgb_metrics.get("recall_fatal", 0))


def task_train_lightgbm(**context):
    """Train LightGBM with class_weight=balanced. Log to MLflow."""
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: train_lightgbm ===")

    from ml.train import train_all_models
    result = train_all_models(models_to_train=["lgbm"])

    lgbm_metrics = result["results"].get("lgbm", {}).get("metrics", {})
    run_id       = result["results"].get("lgbm", {}).get("run_id", "")

    logger.info(
        "LGBM complete: macro-F1=%.4f  recall_fatal=%.4f",
        lgbm_metrics.get("macro_f1", 0),
        lgbm_metrics.get("recall_fatal", 0),
    )
    context["ti"].xcom_push(key="lgbm_run_id",      value=run_id)
    context["ti"].xcom_push(key="lgbm_macro_f1",    value=lgbm_metrics.get("macro_f1", 0))
    context["ti"].xcom_push(key="lgbm_recall_fatal",value=lgbm_metrics.get("recall_fatal", 0))


def task_evaluate_and_select_champion(**context):
    """
    Compare all three models using macro-F1 (primary) and
    recall_fatal (tie-break). Save champion to models/best_model.pkl.
    """
    import logging
    import json
    from pathlib import Path
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: evaluate_and_select_champion ===")

    ti = context["ti"]

    # Pull metrics from XCom
    results_summary = {}
    for model in ["rf", "xgb", "lgbm"]:
        run_id      = ti.xcom_pull(key=f"{model}_run_id")
        macro_f1    = ti.xcom_pull(key=f"{model}_macro_f1")    or 0
        recall_fatal= ti.xcom_pull(key=f"{model}_recall_fatal") or 0

        if run_id:
            results_summary[model] = {
                "run_id":  run_id,
                "macro_f1":    float(macro_f1),
                "recall_fatal":float(recall_fatal),
            }

    if not results_summary:
        raise ValueError("No model results found in XCom")

    # Pick champion: best macro_f1, tiebreak recall_fatal
    champion = max(
        results_summary.items(),
        key=lambda x: (x[1]["macro_f1"], x[1]["recall_fatal"])
    )
    champion_name    = champion[0]
    champion_run_id  = champion[1]["run_id"]
    champion_macro_f1 = champion[1]["macro_f1"]

    logger.info(
        "Champion: %s | macro-F1=%.4f | run_id=%s",
        champion_name, champion_macro_f1, champion_run_id
    )

    context["ti"].xcom_push(key="champion_name",   value=champion_name)
    context["ti"].xcom_push(key="champion_run_id", value=champion_run_id)
    context["ti"].xcom_push(key="champion_macro_f1",value=champion_macro_f1)


def task_register_model(**context):
    """
    Register champion model in MLflow Model Registry.
    Transition previous Production version to Archived.
    Promote new version to Production.
    """
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: register_model_to_mlflow ===")

    ti = context["ti"]
    champion_name    = ti.xcom_pull(key="champion_name")
    champion_run_id  = ti.xcom_pull(key="champion_run_id")
    champion_macro_f1 = ti.xcom_pull(key="champion_macro_f1") or 0
    champion_recall  = ti.xcom_pull(key=f"{champion_name}_recall_fatal") or 0

    if not champion_run_id:
        raise ValueError("champion_run_id not found in XCom")

    from ml.register_model import register_champion
    version = register_champion(
        run_id     = champion_run_id,
        model_name = champion_name,
        metrics    = {
            "macro_f1":     float(champion_macro_f1),
            "recall_fatal": float(champion_recall),
        },
    )
    logger.info(
        "Registered %s as version %s in MLflow Model Registry.",
        champion_name, version
    )
    context["ti"].xcom_push(key="model_version", value=version)


def task_run_monitoring(**context):
    """
    Run full monitoring suite:
    - Feature drift detection (KS-test)
    - Location drift detection
    - Performance evaluation on test set
    Save combined monitoring report to models/monitoring_combined.json.
    """
    import logging
    logger = logging.getLogger("airflow.task")
    logger.info("=== TASK: run_monitoring_checks ===")

    from monitoring.performance_monitor import run_full_monitoring
    report = run_full_monitoring()

    retrain = report.get("retrain_required", False)
    perf    = report.get("performance", {})

    logger.info(
        "Monitoring complete: macro-F1=%.4f | recall_fatal=%.4f | "
        "retrain_required=%s",
        perf.get("macro_f1",     0),
        perf.get("recall_fatal", 0),
        retrain,
    )
    context["ti"].xcom_push(key="retrain_required", value=retrain)
    context["ti"].xcom_push(key="monitor_macro_f1", value=perf.get("macro_f1", 0))


# ── DAG definition ─────────────────────────────────────────────────────────────

with DAG(
    dag_id="ml_training_pipeline",
    description=(
        "Part 2 MLOps — train RF/XGBoost/LightGBM, select champion, "
        "register in MLflow, run monitoring checks."
    ),
    default_args=default_args,
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["traffic", "ml", "mlops", "training"],
    doc_md="""
## ML Training Pipeline (Part 2)

**Prerequisites:** Run `traffic_accident_pipeline` DAG first (Part 1).

**Purpose:** Trains three severity classification models, selects the
champion based on macro-F1 and Fatal recall, registers it in the
MLflow Model Registry, and runs monitoring checks.

**Trigger:** Manual (`schedule=None`). Re-trigger when:
- New STATS19 annual data is published
- Monitoring reports retrain_required=True
- Significant data drift is detected

**Model selection:** macro-F1 (primary), recall_fatal (tie-break).
Fatal recall is prioritised because missing a Fatal accident
(predicting Slight when it is Fatal) is the worst possible error.
""",
) as dag:

    start = EmptyOperator(task_id="start")

    prepare_features = PythonOperator(
        task_id="prepare_features",
        python_callable=task_prepare_features,
        doc_md="Load data, build 15-feature matrix, chronological split.",
    )

    # ── Three models run in parallel ──────────────────────────────────────────
    train_rf = PythonOperator(
        task_id="train_random_forest",
        python_callable=task_train_random_forest,
        doc_md="Train Random Forest with class_weight=balanced.",
    )

    train_xgb = PythonOperator(
        task_id="train_xgboost",
        python_callable=task_train_xgboost,
        doc_md="Train XGBoost with sample_weight for class imbalance.",
    )

    train_lgbm = PythonOperator(
        task_id="train_lightgbm",
        python_callable=task_train_lightgbm,
        doc_md="Train LightGBM with class_weight=balanced.",
    )

    evaluate = PythonOperator(
        task_id="evaluate_and_select_champion",
        python_callable=task_evaluate_and_select_champion,
        doc_md="Compare models: macro-F1 primary, recall_fatal tiebreak.",
    )

    register = PythonOperator(
        task_id="register_model_to_mlflow",
        python_callable=task_register_model,
        doc_md="Register champion in MLflow registry, promote to Production.",
    )

    monitoring = PythonOperator(
        task_id="run_monitoring_checks",
        python_callable=task_run_monitoring,
        doc_md="Feature drift, location drift, performance on test set.",
    )

    ml_complete = EmptyOperator(task_id="ml_pipeline_complete")

    # ── Dependencies ──────────────────────────────────────────────────────────
    start >> prepare_features
    prepare_features >> [train_rf, train_xgb, train_lgbm]
    [train_rf, train_xgb, train_lgbm] >> evaluate
    evaluate >> register >> monitoring >> ml_complete
