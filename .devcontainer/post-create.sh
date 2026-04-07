#!/bin/bash
set -e

# Install uv if not already present
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Backend setup (always use uv, never bare pip)
uv pip install --system -r backend/src/requirements.txt
uv pip install --system -e "backend/.[dev]"

# Frontend setup
(cd frontend && npm ci)

echo "Development environment ready!"
