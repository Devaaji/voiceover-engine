#!/usr/bin/env bash
# Sets up voiceover-engine on this machine. Safe to run again: it only does what is missing.
#
#   bash install.sh        asks before installing a missing system tool (Python, Node.js, FFmpeg)
#   bash install.sh --yes  installs missing system tools without asking
#
# macOS: uses Homebrew. Windows: run it from Git Bash, it uses winget. Linux: uses apt.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

ASSUME_YES=0
# Set by start.sh: never install system tools, and say little.
FROM_START=0
for arg in "$@"; do
  case "$arg" in
    --yes | -y) ASSUME_YES=1 ;;
    --from-start) FROM_START=1 ;;
    --help | -h)
      sed -n '2,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (try --help)"
      exit 1
      ;;
  esac
done

case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) OS=windows ;;
  Darwin) OS=macos ;;
  *) OS=linux ;;
esac
# A venv keeps its programs in Scripts/ on Windows, in bin/ everywhere else.
if [ "$OS" = windows ]; then VENV_BIN="$BACKEND/.venv/Scripts"; else VENV_BIN="$BACKEND/.venv/bin"; fi

say() { [ "$FROM_START" -eq 1 ] || echo "$@"; }
step() { echo "$@"; }

# What the summary at the end shows.
REPORT=()
ok() { REPORT+=("  ok       $1"); }
warn() { REPORT+=("  MISSING  $1"); }

confirm() {
  # $1: the question. Yes with --yes, no when nobody can answer.
  [ "$ASSUME_YES" -eq 1 ] && return 0
  [ -t 0 ] || return 1
  printf '%s [y/N] ' "$1"
  read -r answer
  case "$answer" in y | Y | yes | Yes) return 0 ;; *) return 1 ;; esac
}

# --- System tools: Python, Node.js, FFmpeg -----------------------------------

PYTHON=()
find_python() {
  # The newest Python from 3.13 down to 3.10. On Windows "python3" is usually a Microsoft Store stub,
  # and "py" alone may start an older Python, so the launcher is asked for a version first.
  local candidates candidate
  if [ "$OS" = windows ]; then
    candidates=("py -3.13" "py -3.12" "py -3.11" "py -3.10" "py" "python" "python3")
  else
    candidates=("python3.13" "python3.12" "python3.11" "python3.10" "python3" "python")
  fi
  for candidate in "${candidates[@]}"; do
    # shellcheck disable=SC2086 # "py -3.13" is a program and its option
    if command -v ${candidate%% *} >/dev/null 2>&1 &&
      $candidate -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
      # shellcheck disable=SC2206
      PYTHON=($candidate)
      return 0
    fi
  done
  return 1
}

node_ok() {
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 &&
    [ "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)" -ge 20 ]
}

# FFmpeg 9 or newer: older versions cut the audio short where a pause is filled with room tone (FFmpeg 6.1, Ubuntu
# 24.04's own, made 1.7 s of a 10 s segment; backend/voiceover/ffmpeg_version.py). A build that does not tell its
# version (a git build) is let through.
FFMPEG_MIN_MAJOR=9
ffmpeg_major() { ffmpeg -version 2>/dev/null | head -n 1 | sed -nE 's/^ffmpeg version n?([0-9]+)\..*/\1/p'; }
ffmpeg_version() { ffmpeg -version 2>/dev/null | head -n 1 | sed -nE 's/^ffmpeg version n?([0-9][0-9.]*).*/\1/p'; }
ffmpeg_present() { command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; }
ffmpeg_ok() {
  ffmpeg_present || return 1
  local major
  major="$(ffmpeg_major)"
  [ -z "$major" ] || [ "$major" -ge "$FFMPEG_MIN_MAJOR" ]
}

# How to install each tool on this system. Empty: by hand (printed instead).
install_command() {
  case "$OS:$1" in
    macos:python) echo "brew install python@3.13" ;;
    macos:node) echo "brew install node" ;;
    macos:ffmpeg) if ffmpeg_present; then echo "brew upgrade ffmpeg"; else echo "brew install ffmpeg"; fi ;;
    windows:python) echo "winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements" ;;
    windows:node) echo "winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements" ;;
    windows:ffmpeg)
      if ffmpeg_present; then
        echo "winget upgrade -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements"
      else
        echo "winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements"
      fi
      ;;
    linux:python) echo "sudo apt-get install -y python3 python3-venv python3-pip" ;;
    linux:node) echo "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs" ;;
    # apt's FFmpeg is too old on Ubuntu 24.04 (6.1): a static build is put on the PATH by hand.
    linux:ffmpeg) echo "" ;;
  esac
}

ffmpeg_by_hand() {
  echo "  FFmpeg $FFMPEG_MIN_MAJOR or newer is not in apt on most Linux versions. Use the Docker image (Dockerfile), or put a"
  echo "  static build of FFmpeg $FFMPEG_MIN_MAJOR.x on the PATH: https://github.com/BtbN/FFmpeg-Builds/releases (linux64-gpl-$FFMPEG_MIN_MAJOR.x)."
}

package_manager_ok() {
  case "$OS" in
    macos) command -v brew >/dev/null 2>&1 ;;
    windows) command -v winget >/dev/null 2>&1 ;;
    linux) command -v apt-get >/dev/null 2>&1 ;;
  esac
}

MISSING_TOOLS=()
find_python || MISSING_TOOLS+=(python)
node_ok || MISSING_TOOLS+=(node)
ffmpeg_ok || MISSING_TOOLS+=(ffmpeg)

if [ "${#MISSING_TOOLS[@]}" -gt 0 ]; then
  echo "Missing on this machine:"
  for tool in "${MISSING_TOOLS[@]}"; do
    case "$tool" in
      python) echo "  Python 3.10 or newer (3.13 recommended)" ;;
      node) echo "  Node.js 20 or newer (with npm)" ;;
      ffmpeg)
        if ffmpeg_present; then
          echo "  FFmpeg $FFMPEG_MIN_MAJOR or newer (this one is $(ffmpeg_version): older versions cut the audio short)"
        else
          echo "  FFmpeg $FFMPEG_MIN_MAJOR or newer"
        fi
        ;;
    esac
  done
  echo
  if [ "$FROM_START" -eq 1 ]; then
    echo "Run \"bash install.sh\" to install them, then \"bash start.sh\" again."
    exit 1
  fi
  if ! package_manager_ok; then
    case "$OS" in
      macos)
        echo "Homebrew installs them, and it is not on this Mac yet. Install it first:"
        echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        echo "Then open a new terminal and run \"bash install.sh\" again."
        ;;
      windows)
        echo "winget installs them, and it was not found. It comes with \"App Installer\" from the Microsoft Store."
        echo "Or install them by hand: https://www.python.org/downloads/  https://nodejs.org/  https://www.gyan.dev/ffmpeg/builds/"
        ;;
      linux)
        echo "Install them with your package manager: Python 3.10+ with venv, Node.js 20+."
        ffmpeg_by_hand
        ;;
    esac
    exit 1
  fi
  echo "They can be installed with:"
  for tool in "${MISSING_TOOLS[@]}"; do
    if [ -n "$(install_command "$tool")" ]; then echo "  $(install_command "$tool")"; else ffmpeg_by_hand; fi
  done
  echo
  if ! confirm "Install them now?"; then
    echo "Nothing was installed. Run the commands above, open a new terminal, and run \"bash install.sh\" again."
    exit 1
  fi
  for tool in "${MISSING_TOOLS[@]}"; do
    [ -n "$(install_command "$tool")" ] || continue
    echo
    echo "Installing $tool ..."
    eval "$(install_command "$tool")"
  done
  # A new program is only found by terminals opened after it was installed (always so on Windows).
  hash -r 2>/dev/null || true
  if [ "$OS" = linux ] && ! ffmpeg_ok; then
    echo
    ffmpeg_by_hand
    exit 1
  fi
  if ! find_python || ! node_ok || ! ffmpeg_ok; then
    echo
    echo "Installed. This terminal does not see the new programs yet:"
    echo "close it, open a new one, and run \"bash install.sh\" again to finish."
    exit 0
  fi
fi

ok "$("${PYTHON[@]}" --version 2>&1)"
ok "Node.js $(node -v)"
ok "FFmpeg $(ffmpeg_version)"

# --- Backend ------------------------------------------------------------------

if [ ! -x "$VENV_BIN/python" ] && [ ! -x "$VENV_BIN/python.exe" ]; then
  step "Creating backend/.venv ..."
  "${PYTHON[@]}" -m venv "$BACKEND/.venv"
fi

# Installed when missing, and again when a requirements file changed since.
STAMP="$BACKEND/.venv/.requirements-installed"
if [ ! -f "$STAMP" ] || [ "$BACKEND/requirements.txt" -nt "$STAMP" ] || [ "$BACKEND/requirements-dev.txt" -nt "$STAMP" ]; then
  step "Installing backend packages ..."
  "$VENV_BIN/python" -m pip install --quiet --disable-pip-version-check -r "$BACKEND/requirements-dev.txt"
  touch "$STAMP"
fi
ok "Backend packages"

# .env: made from .env.example the first time, with a new random API_KEY so the API can be used at once.
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  step "Created .env from .env.example."
fi
"$VENV_BIN/python" - "$ROOT/.env" <<'PY'
import re, secrets, sys
from pathlib import Path

env = Path(sys.argv[1])
text = env.read_text(encoding="utf-8")
if re.search(r"^API_KEY=\s*$", text, flags=re.MULTILINE):
    text = re.sub(r"^API_KEY=\s*$", "API_KEY=" + secrets.token_urlsafe(32), text, count=1, flags=re.MULTILINE)
    env.write_bytes(text.encode("utf-8"))
    print("Made a new API_KEY in .env. The test page and other tools send it in the X-API-Key header.")
PY
for key in ELEVENLABS_API_KEY; do
  if grep -Eq "^$key=[[:space:]]*$" "$ROOT/.env" 2>/dev/null; then
    warn "$key in .env. The voice cannot be made without it."
  else
    ok "$key in .env"
  fi
done
if grep -Eq "^ANTHROPIC_API_KEY=[[:space:]]*$" "$ROOT/.env" 2>/dev/null; then
  warn "ANTHROPIC_API_KEY in .env. Needed only for \"rewrite\": true and mode \"content\"."
else
  ok "ANTHROPIC_API_KEY in .env"
fi

# --- Frontend (the test page) ---------------------------------------------------

if [ ! -d "$FRONTEND/node_modules" ] || [ "$FRONTEND/package.json" -nt "$FRONTEND/node_modules/.package-lock.json" ]; then
  step "Installing frontend packages ..."
  (cd "$FRONTEND" && npm install --no-audit --no-fund)
fi
ok "Frontend packages"

[ -f "$FRONTEND/.env.local" ] || cp "$FRONTEND/.env.example" "$FRONTEND/.env.local"

# --- Summary ------------------------------------------------------------------

if [ "$FROM_START" -eq 1 ]; then
  # start.sh only shows what needs attention.
  for line in "${REPORT[@]}"; do
    case "$line" in *"  ok  "*) ;; *) echo "$line" ;; esac
  done
  exit 0
fi

echo
echo "voiceover-engine on this machine:"
for line in "${REPORT[@]}"; do echo "$line"; done
echo
echo "Fill in the keys in .env (ELEVENLABS_API_KEY, and ANTHROPIC_API_KEY for rewrite), then start it with:"
echo "  bash start.sh"
