# ============================================================
# Dockerfile — Traffic Accident Severity Prediction API
# ============================================================
# Builds a container that serves the FastAPI inference service.
#
# Build:
#   docker build -f api/Dockerfile -t traffic-severity-api .
#
# Run standalone:
#   docker run -p 8000:8000 \
#     -v $(pwd)/models:/app/models \
#     -v $(pwd)/.env:/app/.env \
#     traffic-severity-api
#
# Or use docker-compose (recommended):
#   docker-compose up
# ============================================================

FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# ── System dependencies ───────────────────────────────────────
# libgomp1  → required by LightGBM for OpenMP parallel trees
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies ───────────────────────────────
# Copy only requirements first to leverage Docker layer caching.
# If requirements don't change, this layer is not rebuilt.
COPY requirements.txt requirements_ml.txt ./
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    scikit-learn \
    xgboost \
    lightgbm \
    joblib \
    pandas \
    numpy \
    python-dotenv \
    mlflow

# ── Copy application source ───────────────────────────────────
COPY config/  ./config/
COPY ml/      ./ml/
COPY api/     ./api/

# ── Create directories that the app expects ───────────────────
RUN mkdir -p models mlflow data/cleaned

# ── Environment defaults ──────────────────────────────────────
ENV API_HOST=0.0.0.0
ENV API_PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ── Expose port ───────────────────────────────────────────────
EXPOSE 8000

# ── Health check ──────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# ── Start command ─────────────────────────────────────────────
CMD ["uvicorn", "api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]
