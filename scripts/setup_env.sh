#!/usr/bin/env bash
#
# AI Task Manager - Environment Setup Script
# Sets up Python 3.9 virtual environment
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "AI Task Manager - Environment Setup"
echo "========================================"
echo

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Pick Python executable
PYTHON_EXE="${PYTHON_EXE:-}"
if [ -z "$PYTHON_EXE" ]; then
    CANDIDATES=(
        "/c/Users/$USERNAME/AppData/Local/Programs/Python/Python39/python.exe"
        "$USERPROFILE/AppData/Local/Programs/Python/Python39/python.exe"
        "python"
    )
    for candidate in "${CANDIDATES[@]}"; do
        if [ "$candidate" = "python" ]; then
            if command -v python >/dev/null 2>&1; then
                PYTHON_EXE="python"
                break
            fi
        elif [ -f "$candidate" ]; then
            PYTHON_EXE="$candidate"
            break
        fi
    done
fi

if [ -z "$PYTHON_EXE" ]; then
    echo -e "${RED}[ERROR]${NC} Python not found."
    echo "Set PYTHON_EXE and retry, e.g.:"
    echo '  PYTHON_EXE="C:/Users/<YourUser>/AppData/Local/Programs/Python/Python39/python.exe" ./scripts/setup_env.sh'
    exit 1
fi

echo -e "${GREEN}[INFO]${NC} Using Python:"
"$PYTHON_EXE" --version
echo

# Check if venv already exists
if [ -d "venv" ]; then
    if [ "${1:-}" = "--recreate" ]; then
        echo -e "${GREEN}[INFO]${NC} Removing existing virtual environment..."
        rm -rf venv
    else
        echo -e "${GREEN}[INFO]${NC} Keeping existing virtual environment"
    fi
fi

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${GREEN}[INFO]${NC} Creating virtual environment..."
    "$PYTHON_EXE" -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR]${NC} Failed to create virtual environment"
        exit 1
    fi
    echo -e "${GREEN}[SUCCESS]${NC} Virtual environment created"
    echo
fi

# Install dependencies
echo -e "${GREEN}[INFO]${NC} Installing dependencies..."
if ! ./venv/Scripts/python.exe -m pip --version >/dev/null 2>&1; then
    echo -e "${YELLOW}[WARN]${NC} pip module unavailable in venv, bootstrapping with ensurepip..."
    ./venv/Scripts/python.exe -m ensurepip --upgrade
fi

./venv/Scripts/python.exe -m pip install --upgrade pip
./venv/Scripts/python.exe -m pip install -r backend/requirements.txt

if [ $? -ne 0 ]; then
    echo -e "${RED}[ERROR]${NC} Failed to install dependencies"
    exit 1
fi

echo
echo "========================================"
echo -e "${GREEN}[SUCCESS]${NC} Setup completed!"
echo "========================================"
echo
echo "To start the server, run: ./scripts/start_server.sh"
echo "Or manually: cd backend && ../venv/Scripts/python.exe main.py"
echo
