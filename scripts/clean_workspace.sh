#!/usr/bin/env bash
#
# AI Task Manager - Workspace cleanup
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "Cleaning runtime artifacts..."

# Logs and local db files
rm -f ./*.log
rm -f backend/*.log
rm -f frontend/*.log
rm -f ./tasks.db
rm -f backend/tasks.db

# Python caches
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
find . -type d -name ".pytest_cache" -prune -exec rm -rf {} +

# Frontend caches
rm -rf frontend/.next

if [ "${1:-}" = "--deep" ]; then
  echo "Deep cleanup enabled: removing docs and task notes..."
  rm -rf docs
  rm -rf tasks
fi

echo "Cleanup done."
