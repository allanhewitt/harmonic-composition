#!/usr/bin/env bash
# Start the Harmonic Composition app on this Mac and open it in the browser.
#
#   ./start.sh              scripts in Music_Vault; runs made locally and copied to Music_Vault
#   PORT=3001 ./start.sh    another port
#
# First run: creates a private Python environment (.venv) and installs the libraries.
# Later runs: reinstalls only if requirements.txt has changed.
# Folders: HC_PIECES_DIR (scripts), HC_RUNS_DIR (local working runs), HC_EXPORT_DIR (copies; empty = off).
set -euo pipefail
cd "$(dirname "$0")"

# Working files stay on this Mac; finished runs are copied to Music_Vault, and saved scripts live there.
LOCAL="${HC_LOCAL_DIR:-$HOME/Library/Application Support/Harmonic Composition}"
VAULT="${HC_VAULT_DIR:-$HOME/Dropbox/Music_Vault/Composition/Generative Composition/Harmonic Composition}"
export HC_DATA_DIR="${HC_DATA_DIR:-$LOCAL}"
export HC_RUNS_DIR="${HC_RUNS_DIR:-$LOCAL/Runs}"
export HC_PIECES_DIR="${HC_PIECES_DIR:-$VAULT/Pieces}"
export HC_EXPORT_DIR="${HC_EXPORT_DIR-$VAULT/Runs}"     # set HC_EXPORT_DIR= (empty) to turn the copy off
PORT="${PORT:-3000}"
mkdir -p "$HC_RUNS_DIR"
mkdir -p "$HC_PIECES_DIR" 2>/dev/null || echo "Note: cannot create $HC_PIECES_DIR (is Dropbox running?)"

# LilyPond: use one on the PATH (e.g. Homebrew), or a downloaded copy in the home folder.
if ! command -v lilypond >/dev/null 2>&1; then
  for d in "$HOME"/lilypond-*/bin "/Applications/LilyPond.app/Contents/Resources/bin"; do
    if [ -x "$d/lilypond" ]; then export PATH="$d:$PATH"; break; fi
  done
fi

# Python: the newest available of 3.13 ... 3.9.
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.9 or later is needed. Install it with: brew install python@3.12"; exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Creating the Python environment with $($PY --version)…"
  "$PY" -m venv .venv
fi
STAMP=.venv/.requirements.sha
WANT=$(shasum requirements.txt | cut -d' ' -f1)
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$WANT" ]; then
  echo "Installing libraries…"
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
  echo "$WANT" > "$STAMP"
fi

command -v lilypond >/dev/null 2>&1 || echo "Note: LilyPond not found, so no scores will be engraved (MIDI still works). Install with: brew install lilypond"
command -v pdftoppm >/dev/null 2>&1 || echo "Note: pdftoppm not found, so score pages won't show in the browser (the PDF still works). Install with: brew install poppler"

echo "Scripts:      $HC_PIECES_DIR"
echo "Working runs: $HC_RUNS_DIR"
if [ -n "$HC_EXPORT_DIR" ]; then echo "Copies to:    $HC_EXPORT_DIR"; fi
echo "Starting on http://localhost:$PORT  (Ctrl-C to stop)"
( for i in $(seq 1 30); do
    if curl --silent --fail "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
      command -v open >/dev/null 2>&1 && open "http://localhost:$PORT"; exit 0
    fi
    sleep 0.5
  done ) &
exec .venv/bin/python -m uvicorn server:app --app-dir app --host 127.0.0.1 --port "$PORT"
