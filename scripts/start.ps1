# Code Assistant - One-Click Start Script for Windows
# Usage: .\scripts\start.ps1

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Code Assistant - Starting Services" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Check if .env exists
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[!] Created .env from template. Please edit it with your API keys." -ForegroundColor Yellow
        Write-Host "    Required: ANTHROPIC_API_KEY and TAVILY_API_KEY" -ForegroundColor Yellow
        exit 1
    }
}

# Start Docker services
Write-Host "[1/5] Starting Docker services..." -ForegroundColor Green
docker-compose up -d

# Create virtual environment if needed
if (-not (Test-Path "venv")) {
    Write-Host "[2/5] Creating virtual environment..." -ForegroundColor Green
    python -m venv venv
}

# Activate and install dependencies
Write-Host "[3/5] Installing dependencies..." -ForegroundColor Green
& .\venv\Scripts\Activate.ps1
pip install -q -r requirements.txt

# Wait for Oracle to be healthy
Write-Host "[4/5] Waiting for Oracle database to be ready..." -ForegroundColor Green
Write-Host "      (This may take 2-3 minutes on first run)" -ForegroundColor Gray
$timeout = 180
while ($timeout -gt 0) {
    $healthy = docker ps | Select-String "healthy"
    if ($healthy) {
        Write-Host "      Oracle is ready!" -ForegroundColor Green
        break
    }
    Start-Sleep -Seconds 5
    $timeout -= 5
    Write-Host "      Waiting... ($timeout seconds remaining)" -ForegroundColor Gray
}

# Initialize database
Write-Host "[5/5] Initializing database..." -ForegroundColor Green
python -m src.database.seed_data 2>$null

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Starting Code Assistant" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Application: http://localhost:8501" -ForegroundColor White
Write-Host "  Jaeger UI:   http://localhost:16686" -ForegroundColor White
Write-Host ""
Write-Host "  Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

streamlit run streamlit_app.py
