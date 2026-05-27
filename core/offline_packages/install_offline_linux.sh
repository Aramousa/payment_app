#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENDOR_DIR="$PROJECT_ROOT/vendor"
REQUIREMENTS="$PROJECT_ROOT/requirements.txt"
OCR_REQUIREMENTS="$PROJECT_ROOT/requirements-ocr.txt"
OCR_WHEEL_DIR="$SCRIPT_DIR/ocr-wheels"

PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/../venv/bin/python}"
INCLUDE_OCR="${INCLUDE_OCR:-0}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Python executable not found: $PYTHON_BIN"
  echo "Usage: PYTHON_BIN=/path/to/venv/bin/python bash offline_packages/install_offline_linux.sh"
  exit 1
fi

PY_VERSION="$("$PYTHON_BIN" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

case "$PY_VERSION" in
  3.10)
    WHEEL_DIR="$VENDOR_DIR/wheels-linux-py310-django52"
    ;;
  3.12|3.13)
    WHEEL_DIR="$VENDOR_DIR/wheels-linux"
    ;;
  *)
    echo "Unsupported Python version for bundled Linux wheels: $PY_VERSION"
    echo "Ubuntu 22.04 default Python 3.10 is supported. Python 3.12/3.13 is supported if installed intentionally."
    exit 1
    ;;
esac

if [ ! -d "$WHEEL_DIR" ]; then
  echo "Linux wheelhouse not found: $WHEEL_DIR"
  exit 1
fi

"$PYTHON_BIN" -m pip install --no-index --find-links "$WHEEL_DIR" -r "$REQUIREMENTS"

if [ "$INCLUDE_OCR" = "1" ]; then
  if [ "$PY_VERSION" != "3.12" ]; then
    echo "Bundled OCR wheels are currently for Linux Python 3.12."
    echo "Rebuild offline_packages/ocr-wheels for Python $PY_VERSION before enabling OCR."
    exit 1
  fi
  if [ ! -d "$OCR_WHEEL_DIR" ]; then
    echo "OCR wheelhouse not found: $OCR_WHEEL_DIR"
    exit 1
  fi
  "$PYTHON_BIN" -m pip install --no-index --find-links "$OCR_WHEEL_DIR" -r "$OCR_REQUIREMENTS"
fi

echo "Offline Python packages installed successfully."
