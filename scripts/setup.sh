#!/usr/bin/env bash
# One-time setup: Python 3.12 venv with the GenLayer test/lint tools, plus the
# project-local GenLayer CLI. Requires uv (https://docs.astral.sh/uv/) and Node 20+.
set -euo pipefail
cd "$(dirname "$0")/.."
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python --prerelease=allow -r requirements-dev.txt
npm install
npx genlayer network set studio-dev
echo "Done. Run: scripts/glw test"
