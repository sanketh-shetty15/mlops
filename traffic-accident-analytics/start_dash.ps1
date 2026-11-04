Set-Location "C:\Users\Sanketh H R\Projects\MLops\traffic-accident-analytics"
python -m py_compile dashboard/app.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "Syntax OK - starting Streamlit"
    streamlit run dashboard/app.py --server.port 8501
} else {
    Write-Host "Syntax FAILED"
}
