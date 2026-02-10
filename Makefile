.PHONY: help install test lint format e2e-up e2e e2e-down check

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	cd frontend && npm install
	npm install

test: ## Run all tests (frontend + backend unit)
	cd frontend && npx vitest run --passWithNoTests
	PYTHONPATH=backend/src pytest tests/backend/unit -v --tb=short

lint: ## Run all linters
	cd frontend && npm run lint && npm run typecheck && npm run format:check
	ruff check backend/src/

format: ## Format all code (Prettier + ruff format)
	cd frontend && npx prettier --write 'src/**/*.{ts,tsx,js,jsx,css,json}'
	ruff format backend/src/

e2e-up: ## Start LocalStack
	docker compose up -d --wait

e2e: ## Run E2E tests
	PYTHONPATH=backend/src pytest tests/backend/e2e -v -m e2e

e2e-down: ## Stop LocalStack
	docker compose down

check: lint test ## Full CI-equivalent check (lint + test)
