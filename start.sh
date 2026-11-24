#!/usr/bin/env bash
# Runs voiceover-engine: the API (backend) and the test page (frontend).
# Works on macOS and Linux, and on Windows from Git Bash.
#
#   bash start.sh        first checks the installation and finishes what is missing
#   bash start.sh --dev  also restarts the backend when its code changes (not on Windows)
#
# Ports: BACKEND_PORT (8000) and FRONTEND_PORT (3000), from the environment or from .env.
# First time on a machine: run "bash install.sh". It can also install Python, Node.js and FFmpeg.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*)
    IS_WINDOWS=1
    VENV_BIN="$BACKEND/.venv/Scripts"
    ;;
  *)
    IS_WINDOWS=0
    VENV_BIN="$BACKEND/.venv/bin"
    ;;
esac

# --- Make sure everything is installed ----------------------------------------

# Packages that were added since the last run are installed here. It never installs system tools and never asks
# anything: that is what install.sh is for.
echo "Checking the installation ..."
bash "$ROOT/install.sh" --from-start

# A value from .env (the environment wins), without quotes or a Windows line end.
from_env_file() {
  grep -E "^$1=" "$ROOT/.env" 2>/dev/null | head -n 1 | cut -d= -f2- | tr -d '\r' | sed -e 's/^"//' -e 's/"$//' || true
}

BACKEND_PORT="${BACKEND_PORT:-$(from_env_file BACKEND_PORT)}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-$(from_env_file FRONTEND_PORT)}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

# A port another program already listens on is reported, not fought over.
port_busy() {
  "$VENV_BIN/python" -c "
import socket, sys
try:
    socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=0.5).close()
except OSError:
    sys.exit(1)
" "$1"
}
for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  if port_busy "$port"; then
    echo "Port $port is already in use by another program."
    echo "Stop it, or choose other ports, for example:  BACKEND_PORT=8100 FRONTEND_PORT=3100 bash start.sh"
    echo "(or set BACKEND_PORT and FRONTEND_PORT in .env)"
    exit 1
  fi
done

# The test page calls this backend, and the backend lets this page call it.
export NEXT_PUBLIC_API_URL="http://localhost:$BACKEND_PORT"
CORS="${CORS_ORIGINS:-$(from_env_file CORS_ORIGINS)}"
case ",$CORS," in
  *",http://localhost:$FRONTEND_PORT,"*) ;;
  *) CORS="${CORS:+$CORS,}http://localhost:$FRONTEND_PORT" ;;
esac
export CORS_ORIGINS="$CORS"

# --- Run both, stop both on Ctrl+C ------------------------------------------

pids=()
stop() {
  # Git Bash can't signal the children of a Windows program, so end the whole tree.
  if [ -r "/proc/$1/winpid" ]; then
    taskkill //PID "$(cat "/proc/$1/winpid")" //T //F >/dev/null 2>&1 || true
  fi
  pkill -P "$1" 2>/dev/null || true
  kill "$1" 2>/dev/null || true
}
cleanup() {
  trap - INT TERM EXIT
  echo
  echo "Stopping ..."
  # (bash 3.2, on macOS, calls an empty array unbound under set -u)
  for pid in ${pids[@]+"${pids[@]}"}; do
    stop "$pid"
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# The backend does not restart by itself when its code changes: a running job would be lost. "bash start.sh --dev"
# turns that on, for working on the backend. Never on Windows: there the restart sends Ctrl+C to this whole
# terminal, which stops the frontend and this script too.
RELOAD=()
if [ "${1:-}" = "--dev" ]; then
  if [ "$IS_WINDOWS" -eq 1 ]; then
    echo "--dev is ignored on Windows. Restart it after changing backend code."
  else
    RELOAD=(--reload --reload-dir voiceover --reload-dir api --reload-dir jobs --reload-dir writing)
  fi
fi

(cd "$BACKEND" && exec "$VENV_BIN/python" -m uvicorn main:app ${RELOAD[@]+"${RELOAD[@]}"} --port "$BACKEND_PORT") &
pids+=($!)

(cd "$FRONTEND" && exec npm run dev -- --port "$FRONTEND_PORT") &
pids+=($!)

echo
echo "API:       http://localhost:$BACKEND_PORT   (every request needs the X-API-Key header: API_KEY in .env)"
echo "Test page: http://localhost:$FRONTEND_PORT"
echo "Press Ctrl+C to stop both."
echo

# Returns when either process exits, so one crashing stops the other too. (macOS's bash 3.2 has no "wait -n": there
# it waits for both.)
wait -n 2>/dev/null || wait
