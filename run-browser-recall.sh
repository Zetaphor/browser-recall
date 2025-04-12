#!/usr/bin/env bash

cd "$(dirname "$0")"
source "$(dirname "$0")/.venv/bin/activate"
python src/main.py > /dev/null 2>&1 &
echo "Browser Recall started in background with PID $!"