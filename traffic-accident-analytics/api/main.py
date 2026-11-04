"""
api/main.py
------------
FastAPI application that serves severity predictions.

Endpoints
---------
GET  /health                → liveness check
GET  /model/info            → loaded model metadata and metrics
POST /predict/severity      → predict severity for one accident
POST /predict/batch         → predict severity for multiple accidents

Run locally
-----------
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

Run via Docker
--------------
    docker-compose up

Test with curl
--------------
    curl -X POST http://localhost:8000/predict/severity \\
         -H "Content-Type: application/json" \\
         -d '{"accident_hour":8,"weekday_num":0,"accident_month":1,
              "road_type":6,"speed_limit":30}'
"""

import sys
import time
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.schemas import (
    AccidentFeatures,
    PredictionResponse,
    BatchRequest,
    BatchResponse,
    HealthResponse,
    ModelInfoResponse,
)
from config.config import API_HOST, API_PORT, get_logger

logger = get_logger("api")

# ── Global predictor ───────────────────────────────────────────────────────────
# Loaded once at startup, reused for every request.
_predictor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup, warm it up, clean up on shutdown."""
    global _predictor
    logger.info("Loading severity prediction model...")
    try:
        from ml.predict import load_predictor
        _predictor = load_predictor()
        logger.info(
            "Model loaded: %s | features: %d",
            _predictor.model_type,
            len(_predictor.feature_names),
        )
        # ── Warm-up: run one dummy prediction so numpy/sklearn JIT compiles
        # before the first real request hits the endpoint
        import numpy as np
        _warmup = {col: 0.0 for col in _predictor.feature_names}
        _predictor.predict_single(_warmup)
        logger.info("Model warm-up complete — ready to serve.")
    except FileNotFoundError as exc:
        logger.error(
            "Model file not found: %s\n"
            "Run ml/train.py first to train and save the model.",
            exc,
        )
    yield
    logger.info("API shutting down.")


# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Traffic Accident Severity Prediction API",
    description=(
        "Predicts accident severity (Fatal / Serious / Slight) from "
        "road, time, and weather features. "
        "Part 2 of the Traffic Accident Severity Analytics project."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Allow Streamlit dashboard to call this API from a browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Helper ─────────────────────────────────────────────────────────────────────

def _check_model_ready():
    """Raise 503 if model is not loaded."""
    if _predictor is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Model not loaded. "
                "Run 'python ml/train.py' to train the model first, "
                "then restart the API."
            ),
        )


def _features_to_dict(features: AccidentFeatures) -> dict:
    """Convert Pydantic model to plain dict for the predictor."""
    return features.model_dump()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """
    Liveness check.
    Returns 200 with model_loaded=True when the model is ready.
    Returns 200 with model_loaded=False if model file was not found.
    """
    if _predictor is None:
        return HealthResponse(
            status="degraded",
            model_loaded=False,
            model_type="none",
            version="unknown",
        )
    return HealthResponse(
        status="ok",
        model_loaded=True,
        model_type=_predictor.model_type,
        version=str(_predictor.summary.get("champion_model", "1.0")),
    )


@app.get("/model/info", response_model=ModelInfoResponse, tags=["System"])
def model_info():
    """Return metadata about the currently loaded model."""
    _check_model_ready()
    info = _predictor.model_info
    return ModelInfoResponse(**info)


@app.post("/predict/severity", response_model=PredictionResponse,
          tags=["Prediction"])
def predict_severity(features: AccidentFeatures):
    """
    Predict accident severity for a single accident.

    Input features match the STATS19 + Open-Meteo columns used in training.
    Missing optional fields are imputed by the model's preprocessing step.

    Returns predicted severity with confidence and per-class probabilities.
    """
    _check_model_ready()
    t0 = time.perf_counter()

    try:
        result = _predictor.predict_single(_features_to_dict(features))
    except Exception as exc:
        logger.error("Prediction failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    latency_ms = (time.perf_counter() - t0) * 1000
    result["latency_ms"] = round(latency_ms, 2)

    logger.info(
        "Prediction: %s (%.1f%% confidence) | %.1f ms",
        result["severity_label"],
        result["confidence"] * 100,
        latency_ms,
    )

    return PredictionResponse(**result)


@app.post("/predict/batch", response_model=BatchResponse, tags=["Prediction"])
def predict_batch(request: BatchRequest):
    """
    Predict accident severity for a list of accidents in one request.
    More efficient than calling /predict/severity N times.
    """
    _check_model_ready()

    if not request.records:
        raise HTTPException(status_code=400, detail="records list is empty")
    if len(request.records) > 10_000:
        raise HTTPException(
            status_code=400,
            detail="Batch size exceeds maximum of 10,000 records"
        )

    t0 = time.perf_counter()

    import pandas as pd
    rows = [_features_to_dict(r) for r in request.records]
    df   = pd.DataFrame(rows)

    try:
        df_result = _predictor.predict_batch(df)
    except Exception as exc:
        logger.error("Batch prediction failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    latency_ms = (time.perf_counter() - t0) * 1000

    # Build response list
    predictions = []
    for _, row in df_result.iterrows():
        predictions.append(PredictionResponse(
            severity_code  = int(row["severity_code"]),
            severity_label = str(row["severity_label"]),
            confidence     = float(row.get("confidence", 0)),
            probabilities  = {
                "Fatal":   float(row.get("prob_fatal",   0)),
                "Serious": float(row.get("prob_serious", 0)),
                "Slight":  float(row.get("prob_slight",  0)),
            },
            model_type     = _predictor.model_type,
            champion_model = _predictor.summary.get("champion_model", "unknown"),
            latency_ms     = None,
        ))

    logger.info(
        "Batch prediction: %d records | %.1f ms",
        len(predictions), latency_ms
    )

    return BatchResponse(
        predictions=predictions,
        total=len(predictions),
        latency_ms=round(latency_ms, 2),
    )


# ── Dev server entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info",
    )
