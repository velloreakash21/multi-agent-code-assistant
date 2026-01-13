#!/bin/bash
# Code Assistant - One-Click Start Script
# Usage: ./scripts/start.sh

set -e

echo "========================================="
echo "  Code Assistant - Starting Services"
echo "========================================="

# Check if .env exists
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "[!] Created .env from template. Please edit it with your API keys."
        echo "    Required: ANTHROPIC_API_KEY and TAVILY_API_KEY"
        exit 1
    fi
fi

# Check for required API keys
if grep -q "ANTHROPIC_API_KEY=$" .env 2>/dev/null || grep -q "ANTHROPIC_API_KEY=\"\"" .env 2>/dev/null; then
    echo "[!] Please set ANTHROPIC_API_KEY in .env file"
    exit 1
fi

# Start Docker services
echo "[1/5] Starting Docker services..."
docker-compose up -d

# Create virtual environment if needed
if [ ! -d "venv" ]; then
    echo "[2/5] Creating virtual environment..."
    python3 -m venv venv
fi

# Activate and install dependencies
echo "[3/5] Installing dependencies..."
source venv/bin/activate
pip install -q -r requirements.txt

# Wait for Oracle to be healthy
echo "[4/5] Waiting for Oracle database to be ready..."
echo "      (This may take 2-3 minutes on first run)"
timeout=180
while [ $timeout -gt 0 ]; do
    if docker ps | grep -q "healthy"; then
        echo "      Oracle is ready!"
        break
    fi
    sleep 5
    timeout=$((timeout - 5))
    echo "      Waiting... ($timeout seconds remaining)"
done

# Initialize database
echo "[5/5] Initializing database..."
python -m src.database.seed_data 2>/dev/null || true

echo ""
echo "========================================="
echo "  Starting Code Assistant"
echo "========================================="
echo ""
echo "  Application: http://localhost:8501"
echo "  Jaeger UI:   http://localhost:16686"
echo ""
echo "  Press Ctrl+C to stop"
echo "========================================="
echo ""

streamlit run streamlit_app.py
