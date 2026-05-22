#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WHEEL_DIR="$SCRIPT_DIR/python-wheels"
REQUIREMENTS="$PROJECT_ROOT/requirements.txt"

PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/../venv/bin/python}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Python executable not found: $PYTHON_BIN"
  echo "Usage: PYTHON_BIN=/path/to/venv/bin/python bash offline_packages/install_offline_linux.sh"
  exit 1
fi

if [ ! -d "$WHEEL_DIR" ]; then
  echo "Wheelhouse not found: $WHEEL_DIR"
  exit 1
fi

"$PYTHON_BIN" -m pip install --no-index --find-links "$WHEEL_DIR" -r "$REQUIREMENTS"

echo "Offline Python packages installed successfully."
