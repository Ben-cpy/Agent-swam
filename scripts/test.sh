#!/usr/bin/env bash
#
# Run startup tests
#

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

export PYTHONIOENCODING=utf-8

echo "Running startup tests..."
./venv/Scripts/python.exe tests/test_startup.py

if [ $? -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
else
    echo -e "${RED}Tests failed!${NC}"
    exit 1
fi
