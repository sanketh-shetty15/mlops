"""
ml/register_model.py
---------------------
Registers the champion model in the MLflow Model Registry and manages
version lifecycle transitions.

MLflow Model Registry lifecycle
---------------------------------
  Staging    → model being evaluated / tested
  Production → model currently serving live predictions
  Archived   → model replaced by a newer version

Why a registry?
---------------
Without a registry, "the model" is just a .pkl file with no version
history. The registry gives every model version:
  - a unique version number
  - a lifecycle stage
  - a link back to the training run (parameters, metrics, data used)
  - the ability to roll back to any previous version

Usage
-----
    # After training, register and promote the champion:
    python ml/register_model.py --run-id <mlflow_run_id>

    # Or call programmatically after train_all_models():
    from ml.register_model import register_champion
    version = register_champion(run_id, champion_name, metrics)
"""

import sys
import json
import argparse
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    MLFLOW_TRACKING_URI,
    MLFLOW_EXPERIMENT_NAME,
    MLFLOW_REGISTERED_MODEL_NAME,
    MODELS_DIR,
    MIN_ACCEPTABLE_MACRO_F1,
    get_logger,
)

logger = get_logger(__name__)


def _get_client() -> MlflowClient:
    """Return an MlflowClient pointed at our tracking URI."""
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    return MlflowClient(tracking_uri=MLFLOW_TRACKING_URI)


def register_champion(
    run_id: str,
    model_name: str,
    metrics: dict,
) -> str:
    """
    Register the champion model from a training run.

    Steps:
    1. Register model from run artifacts → creates a new version
    2. Add tags and description
    3. Transition any existing Production version to Archived
    4. Transition new version to Production

    Parameters
    ----------
    run_id     : str   — MLflow run ID from the training run
    model_name : str   — e.g. "rf", "xgb", "lgbm"
    metrics    : dict  — e.g. {"macro_f1": 0.45, "recall_fatal": 0.30}

    Returns
    -------
    str : the new model version number
    """
    client = _get_client()
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    macro_f1     = metrics.get("macro_f1", 0)
    recall_fatal = metrics.get("recall_fatal", 0)

    if macro_f1 < MIN_ACCEPTABLE_MACRO_F1:
        logger.warning(
            "Champion macro-F1=%.4f is below minimum threshold %.4f. "
            "Registering but NOT promoting to Production.",
            macro_f1, MIN_ACCEPTABLE_MACRO_F1,
        )

    # ── Step 1: Register the model ────────────────────────────────────────────
    model_uri = f"runs:/{run_id}/model"
    logger.info("Registering model from run %s ...", run_id)

    model_version = mlflow.register_model(
        model_uri=model_uri,
        name=MLFLOW_REGISTERED_MODEL_NAME,
    )
    version_number = model_version.version
    logger.info(
        "Registered: %s version %s",
        MLFLOW_REGISTERED_MODEL_NAME, version_number
    )

    # ── Step 2: Add tags and description ─────────────────────────────────────
    client.update_model_version(
        name=MLFLOW_REGISTERED_MODEL_NAME,
        version=version_number,
        description=(
            f"Champion model: {model_name.upper()} | "
            f"macro-F1={macro_f1:.4f} | "
            f"recall_fatal={recall_fatal:.4f} | "
            f"Run ID: {run_id}"
        ),
    )
    client.set_model_version_tag(
        name=MLFLOW_REGISTERED_MODEL_NAME,
        version=version_number,
        key="model_type",
        value=model_name,
    )
    client.set_model_version_tag(
        name=MLFLOW_REGISTERED_MODEL_NAME,
        version=version_number,
        key="macro_f1",
        value=str(round(macro_f1, 4)),
    )
    client.set_model_version_tag(
        name=MLFLOW_REGISTERED_MODEL_NAME,
        version=version_number,
        key="recall_fatal",
        value=str(round(recall_fatal, 4)),
    )

    # ── Step 3: Archive existing Production version ───────────────────────────
    existing_versions = client.get_latest_versions(
        name=MLFLOW_REGISTERED_MODEL_NAME,
        stages=["Production"],
    )
    for old_version in existing_versions:
        logger.info(
            "Archiving previous Production version: %s",
            old_version.version
        )
        client.transition_model_version_stage(
            name=MLFLOW_REGISTERED_MODEL_NAME,
            version=old_version.version,
            stage="Archived",
            archive_existing_versions=False,
        )

    # ── Step 4: Promote to Production (if above threshold) ───────────────────
    if macro_f1 >= MIN_ACCEPTABLE_MACRO_F1:
        client.transition_model_version_stage(
            name=MLFLOW_REGISTERED_MODEL_NAME,
            version=version_number,
            stage="Production",
            archive_existing_versions=True,
        )
        logger.info(
            "Model version %s promoted to Production.",
            version_number
        )
    else:
        # Below threshold — leave in Staging for manual review
        client.transition_model_version_stage(
            name=MLFLOW_REGISTERED_MODEL_NAME,
            version=version_number,
            stage="Staging",
        )
        logger.warning(
            "Model version %s placed in Staging (below threshold).",
            version_number
        )

    # ── Save registry metadata locally ───────────────────────────────────────
    registry_meta = {
        "registered_model_name": MLFLOW_REGISTERED_MODEL_NAME,
        "version":               version_number,
        "run_id":                run_id,
        "model_type":            model_name,
        "macro_f1":              round(macro_f1, 4),
        "recall_fatal":          round(recall_fatal, 4),
        "stage":                 "Production" if macro_f1 >= MIN_ACCEPTABLE_MACRO_F1
                                 else "Staging",
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODELS_DIR / "registry_metadata.json", "w") as f:
        json.dump(registry_meta, f, indent=2)
    logger.info("Registry metadata saved → %s", MODELS_DIR / "registry_metadata.json")

    return version_number


def get_production_model_info() -> dict:
    """
    Return info about the current Production model version.
    Returns empty dict if no Production version exists.
    """
    client = _get_client()
    try:
        versions = client.get_latest_versions(
            name=MLFLOW_REGISTERED_MODEL_NAME,
            stages=["Production"],
        )
        if not versions:
            logger.info("No Production model version found.")
            return {}
        v = versions[0]
        return {
            "name":    v.name,
            "version": v.version,
            "stage":   v.current_stage,
            "run_id":  v.run_id,
            "description": v.description,
        }
    except Exception as exc:
        logger.warning("Could not query model registry: %s", exc)
        return {}


def list_all_versions() -> list:
    """Return all registered versions of the severity classifier."""
    client = _get_client()
    try:
        versions = client.search_model_versions(
            f"name='{MLFLOW_REGISTERED_MODEL_NAME}'"
        )
        return [
            {
                "version": v.version,
                "stage":   v.current_stage,
                "run_id":  v.run_id,
                "description": v.description,
            }
            for v in versions
        ]
    except Exception as exc:
        logger.warning("Could not list model versions: %s", exc)
        return []


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Register champion model in MLflow Model Registry"
    )
    parser.add_argument("--run-id",    required=True,
                        help="MLflow run ID of the champion training run")
    parser.add_argument("--model-name", default="rf",
                        help="Model type: rf | xgb | lgbm")
    parser.add_argument("--macro-f1",  type=float, default=0.0)
    parser.add_argument("--recall-fatal", type=float, default=0.0)
    args = parser.parse_args()

    metrics = {
        "macro_f1":     args.macro_f1,
        "recall_fatal": args.recall_fatal,
    }
    version = register_champion(args.run_id, args.model_name, metrics)
    print(f"\nRegistered version: {version}")

    prod_info = get_production_model_info()
    print(f"Production model: {prod_info}")
