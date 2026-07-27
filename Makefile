.PHONY: help install test lint format build lock-check e2e-up e2e e2e-down check

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	cd frontend && npm install
	npm install

test: ## Run all tests (frontend + backend unit), with the same coverage gates CI applies
# The backend coverage gate is not on this line: /pytest.ini enables coverage
# and /.coveragerc sets fail_under = 80, so the flags CI used to pass are gone
# from both. The threshold lives in exactly one file now.
	cd frontend && npx vitest run --coverage --passWithNoTests
	PYTHONPATH=backend/src pytest tests/backend/unit -v --tb=short

lint: ## Run all linters
	cd frontend && npm run lint && npm run typecheck && npm run format:check
	ruff check backend/src/ tests/ backend/scripts/
	ruff format --check backend/src/
	mypy --config-file backend/pyproject.toml backend/src/

format: ## Format all code (Prettier + ruff format)
	cd frontend && npx prettier --write 'src/**/*.{ts,tsx,js,jsx,css,json}'
	ruff format backend/src/

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

e2e: ## Run E2E tests
	PYTHONPATH=backend/src pytest tests/backend/e2e -v -m e2e --no-cov

e2e-down: ## Stop MiniStack
	docker compose down

check: lint lock-check test build ## Full CI-equivalent check (lint + lockfile + test + build)
