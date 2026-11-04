"""
ml/predict.py
--------------
Inference pipeline — loads the saved champion model and makes predictions.

The model is a single sklearn Pipeline object containing:
  [0] preprocessor  (SimpleImputer → StandardScaler)
  [1] model         (RF / XGBoost / LightGBM)

Packaging them together ensures the preprocessing applied at inference
always matches the preprocessing applied during training — they cannot
drift apart.

Usage
-----
    from ml.predict import SeverityPredictor
    predictor = SeverityPredictor()
    result = predictor.predict_single({
        "accident_hour": 8,
        "weekday_num": 0,
        ...
    })
"""

import sys
import json
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd
import joblib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.config import (
    MODELS_DIR,
    BEST_MODEL_PATH,
    FEATURE_NAMES_PATH,
    ML_FEATURE_COLUMNS,
    ML_CLASS_NAMES,
    get_logger,
)

logger = get_logger(__name__)


class SeverityPredictor:
    """
    Wraps the saved inference pipeline and exposes simple prediction methods.

    The class loads the model once at initialisation and reuses it for
    all subsequent predictions — no repeated disk reads.
    """

    def __init__(self, model_path: str = None):
        """
        Load the champion model pipeline from disk.

        Parameters
        ----------
        model_path : str, optional
            Path to .pkl file. Defaults to models/best_model.pkl.
        """
        path = Path(model_path) if model_path else BEST_MODEL_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"Model not found at {path}. "
                "Run ml/train.py first to train and save the model."
            )

        self.pipeline    = joblib.load(str(path))
        self.model_path  = str(path)
        self.feature_names = self._load_feature_names()

        # Detect model type from pipeline step
        model_step = self.pipeline.named_steps.get("model")
        self.model_type = type(model_step).__name__.lower()
        # XGBoost returns 0-indexed labels; RF/LGBM return 1-indexed
        self.is_xgb = "xgb" in self.model_type

        # Load training summary for metadata
        summary_path = MODELS_DIR / "training_summary.json"
        self.summary = {}
        if summary_path.exists():
            with open(summary_path) as f:
                self.summary = json.load(f)

        logger.info(
            "SeverityPredictor loaded: %s (model_type=%s)",
            path.name, self.model_type
        )

    def _load_feature_names(self) -> list:
        """Load feature names from JSON file, fall back to config."""
        if FEATURE_NAMES_PATH.exists():
            with open(FEATURE_NAMES_PATH) as f:
                return json.load(f)
        return ML_FEATURE_COLUMNS

    def _to_dataframe(self, input_data: Union[dict, pd.DataFrame]) -> pd.DataFrame:
        """
        Convert a single dict or DataFrame to a properly ordered DataFrame.
        Missing features are filled with NaN (imputer handles them).
        Uses a cached empty template to avoid rebuilding column list every call.
        """
        if isinstance(input_data, dict):
            # Fast path: build directly against cached template
            row = {col: input_data.get(col, np.nan) for col in self.feature_names}
            return pd.DataFrame([row], columns=self.feature_names)
        elif isinstance(input_data, pd.DataFrame):
            df = input_data.copy()
        else:
            raise TypeError(
                f"Expected dict or pd.DataFrame, got {type(input_data)}"
            )

        # Add any missing feature columns as NaN
        for col in self.feature_names:
            if col not in df.columns:
                df[col] = np.nan

        # Select and reorder to match training feature order
        return df[self.feature_names]

    def predict_single(self, input_data: dict) -> dict:
        """
        Make a severity prediction for one accident.
        Uses a single predict_proba call — class is derived from probabilities,
        avoiding a second full pipeline pass.
        """
        X = self._to_dataframe(input_data)

        # Single pass: predict_proba returns both class and confidence
        prob_raw = self.pipeline.predict_proba(X)[0]
        pred_idx = int(np.argmax(prob_raw))   # 0=Fatal, 1=Serious, 2=Slight

        # Remap to 1-indexed severity codes
        severity_code  = pred_idx + 1         # 0→1, 1→2, 2→3
        severity_label = ML_CLASS_NAMES.get(severity_code, "Unknown")
        confidence     = float(prob_raw[pred_idx])

        probabilities = {
            "Fatal":   round(float(prob_raw[0]), 4) if len(prob_raw) > 0 else 0.0,
            "Serious": round(float(prob_raw[1]), 4) if len(prob_raw) > 1 else 0.0,
            "Slight":  round(float(prob_raw[2]), 4) if len(prob_raw) > 2 else 0.0,
        }

        return {
            "severity_code":  severity_code,
            "severity_label": severity_label,
            "confidence":     round(confidence, 4),
            "probabilities":  probabilities,
            "model_type":     self.model_type,
            "champion_model": self.summary.get("champion_model", "unknown"),
        }

    def predict_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Make predictions for a DataFrame of accidents.

        Parameters
        ----------
        df : pd.DataFrame with feature columns

        Returns
        -------
        pd.DataFrame with added columns:
            severity_code, severity_label, confidence,
            prob_fatal, prob_serious, prob_slight
        """
        X = self._to_dataframe(df)
        pred_raw = self.pipeline.predict(X)
        prob_raw = self.pipeline.predict_proba(X)

        result = df.copy()

        if self.is_xgb:
            result["severity_code"] = pred_raw + 1
        else:
            result["severity_code"] = pred_raw

        result["severity_label"] = result["severity_code"].map(ML_CLASS_NAMES)
        result["confidence"]     = np.max(prob_raw, axis=1).round(4)

        if prob_raw.shape[1] >= 3:
            result["prob_fatal"]   = prob_raw[:, 0].round(4)
            result["prob_serious"] = prob_raw[:, 1].round(4)
            result["prob_slight"]  = prob_raw[:, 2].round(4)

        return result

    @property
    def model_info(self) -> dict:
        """Return metadata about the loaded model."""
        return {
            "model_path":    self.model_path,
            "model_type":    self.model_type,
            "champion_model":self.summary.get("champion_model", "unknown"),
            "metrics":       self.summary.get("metrics", {}),
            "feature_count": len(self.feature_names),
            "features":      self.feature_names,
        }


# ── Module-level singleton ─────────────────────────────────────────────────────
# Loaded once when the module is imported — reused for all requests.
# Call load_predictor() to get or create the singleton.

_predictor_instance = None


def load_predictor(model_path: str = None) -> SeverityPredictor:
    """Return (or create) the module-level predictor singleton."""
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = SeverityPredictor(model_path)
    return _predictor_instance


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    predictor = load_predictor()
    print("Model info:", json.dumps(predictor.model_info, indent=2))

    # Sample prediction
    sample = {
        "accident_hour":           8,
        "weekday_num":             0,
        "accident_month":          1,
        "road_type":               6,
        "speed_limit":             30,
        "junction_detail":         13,
        "light_conditions":        1,
        "road_surface_conditions": 1,
        "urban_or_rural_area":     1,
        "number_of_vehicles":      2,
        "number_of_casualties":    1,
        "temperature_2m":         -0.7,
        "precipitation":           0.0,
        "wind_speed_10m":          14.5,
        "weather_code":            2,
    }
    result = predictor.predict_single(sample)
    print("\nSample prediction:")
    print(f"  Severity      : {result['severity_label']} (code {result['severity_code']})")
    print(f"  Confidence    : {result['confidence']:.1%}")
    print(f"  Probabilities : {result['probabilities']}")
