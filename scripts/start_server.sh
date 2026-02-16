#!/usr/bin/env bash
#
# AI Task Manager - Server Startup Script
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo -e "${RED}[ERROR]${NC} Virtual environment not found"
    echo "Please run: ./scripts/setup_env.sh"
    exit 1
fi

echo "========================================"
echo "AI Task Manager - Starting Server"
echo "========================================"
echo

# Check database
if [ ! -f "backend/tasks.db" ]; then
    echo -e "${YELLOW}[WARN]${NC} Database not found, will be created on first run"
fi

# Set environment
export PYTHONIOENCODING=utf-8

echo -e "${GREEN}[INFO]${NC} Starting FastAPI server..."
echo "Server will be available at: http://127.0.0.1:8000"
echo "API docs: http://127.0.0.1:8000/docs"
echo
echo "Press Ctrl+C to stop the server"
echo "========================================"
echo

# Start server
cd backend
../venv/Scripts/python.exe main.py
