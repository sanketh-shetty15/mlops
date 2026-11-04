Set-Location "C:\Users\Sanketh H R\Projects\MLops\traffic-accident-analytics"

Write-Host ""
Write-Host "================================================================"
Write-Host "  TRAFFIC ACCIDENT SEVERITY ANALYTICS"
Write-Host "  Full Project Run — Part 1 + Part 2"
Write-Host "================================================================"
Write-Host ""

# ── PART 1: Data Engineering Pipeline ────────────────────────────────────────
Write-Host ">>> PART 1: Running Data Engineering Pipeline..."
Write-Host "    (using existing cleaned data + weather cache)"
Write-Host ""

python scripts/run_pipeline.py --start-from database --skip-weather-api

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Part 1 pipeline failed. Check logs above."
    exit 1
}

Write-Host ""
Write-Host ">>> Part 1 complete. Verifying database..."
python scripts/verify_database.py

Write-Host ""
Write-Host "================================================================"
Write-Host "  PART 1 DONE"
Write-Host "================================================================"
Write-Host ""

# ── PART 2: ML Training Pipeline ─────────────────────────────────────────────
Write-Host ">>> PART 2: Running ML Training Pipeline..."
Write-Host ""

python scripts/run_ml_pipeline.py --start-from train --skip-registry --skip-monitoring

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Part 2 ML pipeline failed. Check logs above."
    exit 1
}

Write-Host ""
Write-Host "================================================================"
Write-Host "  PART 2 ML TRAINING DONE"
Write-Host "================================================================"
Write-Host ""

# ── Run Monitoring ────────────────────────────────────────────────────────────
Write-Host ">>> Running monitoring checks..."
python scripts/run_ml_pipeline.py --start-from monitoring --skip-registry

Write-Host ""
Write-Host "================================================================"
Write-Host "  ALL STAGES COMPLETE"
Write-Host "================================================================"
Write-Host ""
Write-Host "  Next steps:"
Write-Host "  1. Streamlit dashboard : streamlit run dashboard/app.py"
Write-Host "  2. FastAPI server      : uvicorn api.main:app --port 8000"
Write-Host "  3. MLflow UI           : mlflow ui --backend-store-uri sqlite:///mlflow/mlflow.db"
Write-Host ""
