# Contributing to Pixel Prompt Complete

## Getting Started

1. **Fork** the repository and clone your fork
1. **Install dependencies**:

   ```bash
   make install
   ```

   That is the whole thing. It runs, in order:

   ```bash
   npm install                    # root tooling; this is what installs the git hooks
   cd frontend && npm install     # frontend
   uv venv backend/.venv --python 3.13 --allow-existing
   uv pip install --python backend/.venv/bin/python -r backend/requirements-lock.txt
   uv pip install --python backend/.venv/bin/python -e "backend/.[dev]"
   ```

   **`uv pip`, never bare `pip`.** `uv` refuses to install into an
   externally-managed system Python, and a Makefile should not override that on
   your machine — so the backend goes into `backend/.venv`. CI uses
   `uv pip install --system`, which is correct for a throwaway runner.

   The backend installs from `backend/requirements-lock.txt`, not from
   `requirements.txt`: the latter pins eight direct dependencies and leaves
   every transitive version to whatever the index served that morning.

1. **Verify your setup**: `make check`

   `make check` runs everything `ci.yml` runs except the Docker-backed E2E job:
   lint, docs lint, lockfile drift, tests with coverage, and a production
   frontend build. It invokes the same Makefile targets CI invokes rather than
   copies of their command lines, so the two cannot disagree.

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

- **Formatter**: `ruff format` (line-length 100), gated in CI on
  `backend/src/` only. `ruff check` covers `backend/src/`, `tests/` and
  `backend/scripts/`. The asymmetry is deliberate: reformatting the test tree
  produces a diff no reviewer reads, and drift there has caused no observed
  problem
- **Linter**: `ruff check` with rules E, F, W, I. Configured in
  `backend/pyproject.toml`; `ruff.toml` at the repository root extends it so
  the Python outside `backend/` is held to the same rules
- **Type checking**: `mypy --config-file backend/pyproject.toml backend/src/`,
  which runs in CI. Read "The mypy ratchet" below before fixing anything it
  reports
- **Target**: Python 3.13

#### The mypy ratchet

`backend/pyproject.toml` carries a per-module override list. Every module on it
had errors before mypy was wired into CI, and each entry names the **specific
error codes** that module still reports rather than blanket-ignoring it — so a
new class of error in a listed module still fails the build.

Two things follow:

- **Errors you see in a listed module are recorded debt, not something you
  broke.** You are not expected to fix them to land an unrelated change.
- **Modules come off the list. Nothing goes on it.** Adding a module to make a
  build pass is the thing the list exists to prevent. Fix the file, or narrow
  its entry to the codes it genuinely still needs.

The header of that section records the error count at the time it was written,
so the direction is auditable.

### TypeScript (Frontend)

- **Formatter**: Prettier (singleQuote, trailingComma all, printWidth 100)
- **Linter**: ESLint (flat config), covering the `.ts`/`.tsx` source
- **Type checking**: `npm run typecheck` — `tsc --noEmit` for the app plus
  `tsconfig.node.json` for the build configuration
- **Framework**: React 19, Zustand 5, Tailwind CSS 4

### Pre-commit Hooks

Husky runs automatically on commit:

- **pre-commit**: lint-staged (Prettier + ESLint for frontend, ruff for backend)
- **commit-msg**: commitlint (conventional commits)

## Testing Requirements

### Backend Unit Tests

Use moto for S3 mocking. Assert on observable behavior, not mock call_args:

```bash
PYTHONPATH=backend/src pytest tests/backend/unit -v                    # the suite
PYTHONPATH=backend/src pytest tests/backend/unit/test_x.py --no-cov    # one file
```

Run them from the repository root. Running from `backend/` changes pytest's
rootdir, breaks fixture discovery, and measures coverage of nothing.

**`moto` is not thread-safe.** Do not write tests that drive it from several
threads: a failure is as likely to be moto's shared state as the code under
test. Exercise concurrency by stubbing the S3 client with a
`ClientError({"Error": {"Code": "PreconditionFailed"}})` side effect, or use
real S3 against MiniStack in the E2E suite.

### Backend E2E Tests

Require MiniStack (Docker):

```bash
make e2e-up
make e2e        # supplies the same environment ci.yml's e2e job supplies
make e2e-down
```

### Frontend Tests

Vitest + React Testing Library:

```bash
cd frontend && npm test
```

### Test Coverage

Thresholds are **not restated here**. They have gone stale in this document
twice, and a number written in two places is a number that disagrees with
itself. Read them from the file that enforces them:

- **Backend:** `.coveragerc` (`fail_under`). Coverage is enabled by default in
  `pytest.ini`, so a bare `pytest tests/backend/unit` is already gated and no
  invocation passes `--cov-fail-under`. One consequence: running a single test
  file exits 1 on the floor — add `--no-cov` for that.
- **Frontend:** `frontend/vite.config.ts`, under `test.coverage.thresholds`.
  Run `npm run test:coverage`.

Neither may be lowered to make a build pass. All new code must include tests.

## Commit Message Format

We use [Conventional Commits](https://www.conventionalcommits.org/). The commit-msg hook enforces this.

### Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type       | When to use                             |
| ---------- | --------------------------------------- |
| `feat`     | New feature                             |
| `fix`      | Bug fix                                 |
| `docs`     | Documentation only                      |
| `style`    | Formatting (no code change)             |
| `refactor` | Code change that neither fixes nor adds |
| `perf`     | Performance improvement                 |
| `test`     | Adding or updating tests                |
| `build`    | Build system or dependencies            |
| `ci`       | CI configuration                        |
| `chore`    | Maintenance tasks                       |
| `revert`   | Reverting a previous commit             |

### Examples

```
feat: add outpaint support for Gemini model
fix(iam): grant the Lambda role the private/* prefix it writes to
test(e2e): add iteration limit enforcement test
docs: update API endpoint table in CLAUDE.md
```

## PR Process

1. Fill out [the PR template](.github/PULL_REQUEST_TEMPLATE.md). It asks what
   changed and why, and — the part that matters — the commands you ran and
   what they printed. "Tested locally" is not evidence.
1. Ensure CI passes (lint, typecheck, types, tests, build, E2E, docs lint).
   Note that the `changes` paths filter skips the frontend and backend jobs
   when their paths are untouched, and a skipped job counts as passing — so a
   green check does not always mean the suite ran on your change.
1. Request review from `@HatmanStack`
1. **PRs are merged, not squashed.** There are 109 merge commits in this
   repository's history, and that is deliberate: the commit bodies here carry
   real value — `5cf7999` records a review suggestion that was declined, with
   the reasoning; `3a08adb` proves two fixes are independently necessary by
   reverting one and reporting the delta. Squashing would destroy exactly
   that. Write commit bodies worth keeping: what changed and why, closing with
   the evidence it works rather than the claim.

## Versioning

`CHANGELOG.md` and the git tags are the release record, and
`backend/pyproject.toml`'s `version` tracks the newest released section. The
other two version fields are inert: the root `package.json` and
`frontend/package.json` are both `private: true` and are never published, so
their `version` values (`1.0.0` and `0.0.0`) mean nothing and are deliberately
not kept in step. Do not "fix" them to match — that would imply a coupling that
does not exist.

Open work this repository has consciously deferred is listed in
[docs/follow-ups/2026-07-audit-deferred.md](docs/follow-ups/2026-07-audit-deferred.md),
each entry with the condition that retires it. Architectural decisions that
govern live code are in [docs/adr/](docs/adr/README.md).
