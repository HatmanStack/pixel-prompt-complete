# Contributing to Pixel Prompt Complete

## Getting Started

1. **Fork** the repository and clone your fork
2. **Install dependencies**:
   ```bash
   # Frontend
   cd frontend && npm install

   # Backend (dev dependencies)
   cd backend && uv pip install -e ".[dev]"

   # Root (husky, lint-staged, commitlint)
   npm install
   ```
3. **Verify your setup**: `make check`

## Development Workflow

1. Create a branch from `main`:
   ```bash
   git checkout -b feat/your-feature main
   ```
2. Make your changes with conventional commits (see below)
3. Run tests and linting before pushing:
   ```bash
   make check
   ```
4. Push and open a Pull Request against `main`

## Coding Standards

### Python (Backend)

- **Formatter**: `ruff format` (line-length 100)
- **Linter**: `ruff check` with rules E, F, W, I
- **Type checking**: `mypy` (gradual typing)
- **Target**: Python 3.13

### TypeScript (Frontend)

- **Formatter**: Prettier (singleQuote, trailingComma all, printWidth 100)
- **Linter**: ESLint (flat config)
- **Type checking**: `tsc --noEmit`
- **Framework**: React 19, Zustand 5, Tailwind CSS 4

### Pre-commit Hooks

Husky runs automatically on commit:
- **pre-commit**: lint-staged (Prettier + ESLint for frontend, ruff for backend)
- **commit-msg**: commitlint (conventional commits)

## Testing Requirements

### Backend Unit Tests

Use moto for S3 mocking. Assert on observable behavior, not mock call_args:

```bash
PYTHONPATH=backend/src pytest tests/backend/unit -v
```

### Backend E2E Tests

Require LocalStack (Docker):

```bash
make e2e-up
PYTHONPATH=backend/src pytest tests/backend/e2e -v -m e2e
make e2e-down
```

### Frontend Tests

Vitest + React Testing Library:

```bash
cd frontend && npm test
```

## Commit Message Format

We use [Conventional Commits](https://www.conventionalcommits.org/). The commit-msg hook enforces this.

### Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting (no code change) |
| `refactor` | Code change that neither fixes nor adds |
| `perf` | Performance improvement |
| `test` | Adding or updating tests |
| `build` | Build system or dependencies |
| `ci` | CI configuration |
| `chore` | Maintenance tasks |
| `revert` | Reverting a previous commit |

### Examples

```
feat: add outpaint support for Gemini model
fix(rate-limit): prevent race condition in atomic increment
test(e2e): add iteration limit enforcement test
docs: update API endpoint table in CLAUDE.md
```

## PR Process

1. Fill out the PR template
2. Ensure CI passes (lint, typecheck, tests, E2E)
3. Request review from `@HatmanStack`
4. PRs are squash-merged to keep history clean
