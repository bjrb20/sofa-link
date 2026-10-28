#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
# macOS ships an older python3; prefer $PYTHON, then the newest python3.1x on PATH.
python=${PYTHON:-}
if [[ -z $python ]]; then
  for candidate in python3.14 python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null &&
        "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
      python=$candidate
      break
    fi
  done
fi
if [[ -z $python ]]; then
  echo 'Python 3.12 or later is required. Install it, or set PYTHON=/path/to/python3.12.' >&2
  exit 1
fi
"$python" - <<'PY'
import platform
import sys
from fetch_core import target
if sys.version_info < (3, 12):
    raise SystemExit('Python 3.12 or later is required')
try:
    architecture, _ = target()
except ValueError as error:
    raise SystemExit(str(error)) from error
if platform.system() == 'Darwin' and int(platform.mac_ver()[0].split('.')[0]) < 14:
    raise SystemExit('macOS 14 or later is required by the bundled streaming dependencies')
print(f'Preparing {platform.system()} {architecture} with Python {platform.python_version()}')
PY
"$python" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python fetch_core.py "$@"
mkdir -p runtime/system/pcsx2/bios runtime/saves
echo 'Setup complete. See README.md to start the host with your original CUE/BIN files.'
