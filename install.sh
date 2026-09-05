#!/usr/bin/env bash
# Lightweight install check for bug-bounty-ai-pipeline
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "== bug-bounty-ai-pipeline install check =="

echo "1. Checking Python..."
if ! command -v python3 &>/dev/null; then
  echo "   ERROR: python3 not found. Install Python 3.10+."
  exit 1
fi
PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "   OK: python3 ($PY_VER)"

echo "2. Checking uv..."
if ! command -v uv &>/dev/null; then
  echo "   ERROR: uv not found."
  echo "   Install: https://docs.astral.sh/uv/getting-started/installation/"
  echo "   Quick: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
echo "   OK: $(uv --version)"

echo "3. Portfolio config..."
if [ ! -f config/portfolio.yaml ]; then
  if [ -f config/portfolio.yaml.example ]; then
    cp config/portfolio.yaml.example config/portfolio.yaml
    echo "   Created config/portfolio.yaml from example — edit before /portfolio discover."
  fi
fi

if [ ! -f config/.env.portfolio ] && [ ! -f .env ]; then
  if [ -f config/.env.portfolio.example ]; then
    cp config/.env.portfolio.example config/.env.portfolio
    echo "   Created config/.env.portfolio from example — add API keys before Phase 1."
  fi
fi

echo "4. Smoke test (optional deps)..."
PYTHONPATH=. uv run --with pytest python -m pytest tests/test_scaffold.py -q || {
  echo "   WARN: pytest smoke failed — check PYTHONPATH and Python version."
}

echo ""
echo "Done. Next steps:"
echo "  1. Open this folder in Cursor"
echo "  2. Copy config examples if not done: config/portfolio.yaml, config/.env.portfolio"
echo "  3. Optional companions: npx skills add shenwell/ai-agent-skills --skill memo-session-skill -g -a cursor -y"
echo "  4. Phase 1: /portfolio discover  |  Phase 2: /new <platform> <slug>"
