#!/usr/bin/env bash
#
# AI Task Manager - Environment Setup Script
# Sets up Python 3.9.13 virtual environment
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

# Python executable path
PYTHON_EXE="C:/Users/15225/AppData/Local/Programs/Python/Python39/python.exe"

# Check if Python 3.9.13 exists
if [ ! -f "$PYTHON_EXE" ]; then
    echo -e "${RED}[ERROR]${NC} Python 3.9.13 not found at: $PYTHON_EXE"
    echo "Please install Python 3.9.13 or update the path in this script"
    exit 1
fi

echo -e "${GREEN}[INFO]${NC} Using Python:"
"$PYTHON_EXE" --version
echo

# Check if venv already exists
if [ -d "venv" ]; then
    echo -e "${YELLOW}[WARN]${NC} Virtual environment already exists"
    read -p "Do you want to recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}[INFO]${NC} Removing existing virtual environment..."
        rm -rf venv
    else
        echo -e "${GREEN}[INFO]${NC} Keeping existing virtual environment"
        # Skip to installation
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
./venv/Scripts/pip.exe install --upgrade pip
./venv/Scripts/pip.exe install -r backend/requirements.txt

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

read -p "Press any key to continue..."
