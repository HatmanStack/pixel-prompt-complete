.PHONY: help install test test-backend lint format build lock-check e2e-up e2e e2e-down check

# Where the Python toolchain lives. `make install` creates backend/.venv and
# installs into it, so nothing here needs an activated environment; CI installs
# with `uv pip install --system`, where the same names are on PATH and there is
# no backend/.venv. Each variable falls back, so this file runs the identical
# commands in both places instead of keeping a second copy of them in ci.yml.
# Override on the command line if your environment is neither: make test
# PYTEST=/path/to/pytest
VENV := backend/.venv
VENV_BIN := $(VENV)/bin
PYTEST := $(shell test -x $(VENV_BIN)/pytest && echo $(VENV_BIN)/pytest || echo pytest)
RUFF := $(shell test -x $(VENV_BIN)/ruff && echo $(VENV_BIN)/ruff || echo ruff)
MYPY := $(shell test -x $(VENV_BIN)/mypy && echo $(VENV_BIN)/mypy || echo mypy)

help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}'

# Root npm install goes FIRST: it installs husky (package.json "prepare"), so
# the git hooks exist before anything else runs. This target used to run
# `npm install` twice and no Python at all, while CONTRIBUTING told a new
# contributor to verify the setup with `make check` -- which runs pytest.
#
# The backend goes into backend/.venv rather than --system: uv refuses to
# install into an unmanaged system Python (PEP 668 marks most distributions
# externally-managed) and installing there anyway is not something a Makefile
# should do to a contributor's machine. CI keeps using --system, which is
# correct for a throwaway runner. uv pip, never bare pip -- CLAUDE.md.
install: ## Install all dependencies (root tooling, frontend, backend venv)
	npm install
	cd frontend && npm install
	uv venv $(VENV) --python 3.13 --allow-existing
	uv pip install --python $(VENV_BIN)/python -r backend/requirements-lock.txt
	uv pip install --python $(VENV_BIN)/python -e "backend/.[dev]"

test: ## Run all tests (frontend + backend unit), with the same coverage gates CI applies
	cd frontend && npx vitest run --coverage --passWithNoTests
	$(MAKE) test-backend

# The coverage gate is not on this line: /pytest.ini enables coverage and
# /.coveragerc sets fail_under = 80, so the flags CI used to pass are gone from
# both. The threshold lives in exactly one file now. `npm run test:backend`
# calls this target rather than repeating the command.
test-backend: ## Run the backend unit suite only
	PYTHONPATH=backend/src $(PYTEST) tests/backend/unit -v --tb=short

lint: ## Run all linters
	cd frontend && npm run lint && npm run typecheck && npm run format:check
	$(RUFF) check backend/src/ tests/ backend/scripts/
	$(RUFF) format --check backend/src/
	$(MYPY) --config-file backend/pyproject.toml backend/src/

format: ## Format all code (Prettier + ruff format)
	cd frontend && npx prettier --write 'src/**/*.{ts,tsx,js,jsx,css,json}'
	$(RUFF) format backend/src/

build: ## Build the production frontend bundle, as CI does
	cd frontend && npm run build

# Compiles INTO the committed path on purpose: uv reads an existing output file
# as a preference set, so unrelated upstream releases do not move the pins and
# only a real requirements.txt change fails this. Compiling to a scratch path
# would re-resolve from scratch and go red the first time any transitive
# dependency published a version.
#
# Only the pin lines are compared. The `# via` provenance annotations differ
# between uv versions (verified: 0.11.7 attributes distro to google-genai where
# the previous run did not) and CI installs whatever uv is current, so diffing
# the comments would fail on uv's release schedule rather than on this
# repository's dependencies. The file is restored either way -- this target
# reports, it does not rewrite your tree.
#
# ci.yml runs this same target rather than a copy of these lines.
lock-check: ## Check backend/requirements-lock.txt is current (needs network)
	@cp backend/requirements-lock.txt /tmp/pp-lock-committed.txt
	@uv pip compile backend/src/requirements.txt -o backend/requirements-lock.txt --no-header --quiet
	@grep -v '^[[:space:]]*#' /tmp/pp-lock-committed.txt > /tmp/pp-lock-committed-pins.txt
	@grep -v '^[[:space:]]*#' backend/requirements-lock.txt > /tmp/pp-lock-fresh-pins.txt
	@cp /tmp/pp-lock-committed.txt backend/requirements-lock.txt
	@diff -u /tmp/pp-lock-committed-pins.txt /tmp/pp-lock-fresh-pins.txt \
	  || (echo "backend/requirements-lock.txt is stale. Rerun:" \
	      && echo "  uv pip compile backend/src/requirements.txt -o backend/requirements-lock.txt --no-header" \
	      && exit 1)

e2e-up: ## Start MiniStack
	docker compose up -d --wait

e2e: ## Run E2E tests (needs Docker: `make e2e-up` first)
	PYTHONPATH=backend/src $(PYTEST) tests/backend/e2e -v -m e2e --no-cov

e2e-down: ## Stop MiniStack
	docker compose down

check: lint lock-check test build ## Full CI-equivalent check (lint + lockfile + test + build)
