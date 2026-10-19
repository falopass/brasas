#!/usr/bin/env sh
# BRASA Chile — inicio en macOS/Linux. Uso: ./start.sh [puerto]
set -e
cd "$(dirname "$0")"
PORT="${1:-8000}"
command -v python3 >/dev/null || { echo "Se necesita Python 3.12 o superior."; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || { echo "Tu Python es anterior a 3.12."; exit 1; }
[ -f .env ] || cp .env.example .env
[ -x .venv/bin/python ] || python3 -m venv .venv
HASH="$(python3 -c 'import hashlib;print(hashlib.sha256(open("requirements.txt","rb").read()).hexdigest())')"
if [ "$(cat .venv/requirements.sha 2>/dev/null)" != "$HASH" ]; then
  echo "Instalando dependencias..."
  .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
  echo "$HASH" > .venv/requirements.sha
fi
echo "BRASA Chile en http://127.0.0.1:$PORT  (Ctrl+C para salir)"
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port "$PORT"
