<div align="center">
<h1>Pixel Prompt Complete</h1>

[![CI](https://github.com/HatmanStack/pixel-prompt-complete/actions/workflows/ci.yml/badge.svg)](https://github.com/HatmanStack/pixel-prompt-complete/actions/workflows/ci.yml)
<a href="https://www.apache.org/licenses/LICENSE-2.0.html"><img src="https://img.shields.io/badge/license-Apache2.0-blue" alt="Apache 2.0 license" /></a>
<a href="https://reactjs.org/"><img src="https://img.shields.io/badge/React-19-61DAFB" alt="React 19" /></a>
<a href="https://aws.amazon.com/lambda/"><img src="https://img.shields.io/badge/AWS-Lambda-FF9900" alt="AWS Lambda" /></a>
<a href="https://docs.aws.amazon.com/serverless-application-model/"><img src="https://img.shields.io/badge/AWS-SAM-FF9900" alt="AWS SAM" /></a>

<p><b>Keep refining an image across four AI models, in one conversation</b></p>
<p><a href="https://production.d2iujulgl0aoba.amplifyapp.com/">Live Demo</a></p>

** THIS REPO IS IN ACTIVE DEVELOPMENT AND WILL CHANGE OFTEN **
</div>

## What is this?

Most tools that run several image models give you a grid and stop there. Pixel
Prompt keeps going: every model gets its own conversation thread with a
maintained context window, so you can refine one model's output over several
turns while comparing it against the others, and outpaint any of them to a new
aspect ratio through the same interface.

The four-way comparison is the entry point. The part that is hard to build, and
hard to copy, is what happens after it:

- **Per-model conversation threads.** Refine Gemini's output five times while
  Firefly's stays where it was. Each thread keeps a rolling context window, so
  turn five still knows what turn one asked for.
- **One refinement interface, four different provider APIs.** Each model
  reaches image editing by a different route, and DALL-E 3 cannot edit at all,
  so iteration silently uses `gpt-image-1` instead. That is four separate edit
  paths behind one control.
- **Cross-model outpaint.** Expand any model's image to a new aspect ratio
  without leaving the thread.
- **It learns which model suits you.** Generating gives you four images you did
  not choose between. Refining one is a choice, and a costly one, so the app
  records it. Over time that answers a question a single-model tool cannot
  ask: which model is actually best for _your_ prompts.

Submit a prompt and you get Gemini, Nova Canvas, DALL-E 3 and Firefly side by
side. Deployed on AWS with Lambda, S3 and CloudFront, no servers to manage.

## Architecture

```text
  React App (Vite/TS)
        │
        │  POST /generate
        ▼
  API Gateway (HttpApi)          29s integration timeout — an AWS hard cap, not adjustable
        │
        ▼
  Lambda — request path
  validate → resolve tier → spend ceilings → age gate → quota →
  reserve per-model cost slots → create session in S3
        │
        ├──►  202 {sessionId, prompt, models}  ──►  client polls GET /status/{sessionId}
        │
        └──►  async self-invoke (InvocationType=Event)
                     │
                     ▼
              Lambda — generate worker      900s function timeout, no gateway in front
              ThreadPoolExecutor(GENERATE_THREAD_WORKERS, default 4)
                     │
         ┌───────────┼───────────┬───────────┐
         ▼           ▼           ▼           ▼
      Gemini       Nova      DALL-E 3     Firefly
     (Google)      (AWS)     (OpenAI)     (Adobe)
         └───────────┴───────────┴───────────┘
                     │
                     ▼
                    S3        sessions/ (public gallery) · private/ (paid tier)
                     │
                     ▼
                CloudFront (CDN)
```

**The request returns before any provider is called.** That is the single most
important thing about the system's shape: a four-provider fan-out routinely
outlives the gateway's 29-second ceiling, so `POST /generate` answers with 202
as soon as the session exists and hands the generation to an asynchronous
worker invocation of itself. `/iterate` and `/outpaint` are one provider call
each and are answered inside the request.

`GENERATE_ASYNC=false` restores the old synchronous behaviour. It is the only
mode that works where there is no Lambda service to self-invoke, which is why
`sam local start-api` and the MiniStack E2E suite use it.

## Quick Start (Frontend Only)

This repository is a **submodule** of the parent
[`pixel-prompt`](https://github.com/HatmanStack/pixel-prompt) repository. Clone
it directly, or clone the parent recursively:

```bash
# Directly
git clone https://github.com/HatmanStack/pixel-prompt-complete.git

# Or as part of the parent repository
git clone --recursive https://github.com/HatmanStack/pixel-prompt.git
```

```bash
cd pixel-prompt-complete/frontend
npm install
npm run dev
# Open http://localhost:3000
```

You'll need a deployed backend to generate images. See Full Stack Setup below.

## Full Stack Setup

### Prerequisites

- **Node.js** v24 LTS (via nvm)
- **Python** 3.13+ (via uv or pyenv)
- **uv** — Python dependencies install with `uv pip`, never bare `pip`
- **AWS CLI** configured (`aws configure`)
- **AWS SAM CLI** for serverless deployment
- **Docker**, for the MiniStack-backed E2E suite only

Install everything with one command from the repository root:

```bash
make install
```

That installs the root tooling (which is what puts the git hooks in place), the
frontend, and a `backend/.venv` from `backend/requirements-lock.txt`.

### Configuration: `AUTH_ENABLED` is mandatory

**`AUTH_ENABLED` has no default and the Lambda raises at import without it.**
Deploy with it unset and every request fails at cold start, before any handler
runs. There is deliberately no default because there is no safe value to guess:
`false` serves unauthenticated traffic and `true` requires Cognito plus a guest
token secret. Failing at import forces the choice into the deploy parameters,
where it is reviewable.

Set it in `backend/.env.deploy`, which `npm run deploy` reads, or as a SAM
parameter override. There are two backend templates and they are not
interchangeable:

- [`backend/.env.deploy.example`](backend/.env.deploy.example) — **copy this to
  `backend/.env.deploy`.** It holds exactly the keys `npm run deploy` acts on,
  and it is the file the script names when `.env.deploy` is missing.
- [`backend/.env.example`](backend/.env.example) — the reference surface: every
  variable the backend reads, with the code's defaults, around ninety of them.
  Read it to find out what exists. Do not copy it to `.env.deploy`, where most
  of it would be silently ignored.

[`CLAUDE.md`](CLAUDE.md#environment-variables) carries that same surface as
tables. It is not duplicated here: a duplicated table is a table that drifts.

The frontend has its own, much smaller surface: copy
[`frontend/.env.example`](frontend/.env.example) to `frontend/.env`.

### Modes

|                    | Open-source mode                                  | Full tier system                                         |
| ------------------ | ------------------------------------------------- | -------------------------------------------------------- |
| `AUTH_ENABLED`     | `false`                                           | `true`                                                   |
| `BILLING_ENABLED`  | `false`                                           | `true` (requires auth)                                   |
| External services  | none                                              | Cognito, Stripe, optionally SES and Cloudflare Turnstile |
| Callers resolve to | the `anon` tier, keyed on a hash of the source IP | guest / free / paid, keyed on identity                   |

Open-source mode disables auth, billing, CAPTCHA, email notifications and the
admin API. A contributor can run the whole stack without any paid-tier setup.

**Open does not mean unlimited.** `AUTH_ENABLED` gates _identity only_. Quota,
per-model daily caps and dollar spend metering apply in every configuration,
because "I have no Cognito" and "I want no spend limits" are unrelated
statements and one flag should not assert both. Two consequences worth knowing
before you deploy:

- Open-source mode **still reads and writes DynamoDB** — metering requires
  persistence. SAM creates the users table whichever way the flags are set; an
  unused table costs nothing.
- The `$25/day` and `$500/month` spend ceilings and the per-model daily caps
  are on by default and are the last thing between a misconfiguration and an
  unbounded provider bill. Set them to `0` to disable, consciously.

### Deploy the backend

`npm run deploy` is the live entrypoint. It reads `backend/.env.deploy`, checks
your AWS and SAM prerequisites, builds, deploys, and writes the resulting API
endpoint into `frontend/.env`:

```bash
cp backend/.env.deploy.example backend/.env.deploy   # then edit it — AUTH_ENABLED is mandatory
npm run deploy
```

It forwards what it reads as SAM parameter overrides: `AUTH_ENABLED`, the
prompt-model settings, the four models' enable/id/credential variables,
`ALARM_EMAIL` and the two spend ceilings. Anything else you want to change is a
SAM parameter, set with `sam deploy --guided` or explicit overrides:

```bash
cd backend
sam build
sam deploy --guided    # first time; writes samconfig.toml, which is not committed
sam deploy             # subsequently
```

### Deploy the frontend

**There is no frontend deploy target in this repository.** `npm run deploy`
ends by printing "Deploy frontend to your hosting platform", and that is
accurate — building and uploading the bundle is yours to arrange:

```bash
cd frontend
npm run build          # writes dist/, no source maps
# then upload dist/ to your host (S3 + CloudFront, Amplify, Netlify, …)
```

### Run the frontend locally

```bash
cd frontend
npm install
npm run dev
```

## Development

`make check` from the repository root runs everything CI runs except the
Docker-backed E2E job. Run it before pushing.

### Repository-root commands

| Command           | Description                                                               |
| ----------------- | ------------------------------------------------------------------------- |
| `make install`    | Root tooling (installs the git hooks), frontend, and `backend/.venv`      |
| `make check`      | `lint` + `docs-lint` + `lock-check` + `test` + `build`                    |
| `make lint`       | Frontend lint/typecheck/format-check, ruff check, ruff format check, mypy |
| `make test`       | Frontend Vitest with coverage, then the backend unit suite                |
| `make build`      | Production frontend bundle                                                |
| `make docs-lint`  | markdownlint over the repository's Markdown                               |
| `make lock-check` | Fail if `backend/requirements-lock.txt` is stale (needs network)          |
| `make help`       | List every target                                                         |

### Frontend commands

| Command                 | Description                                             |
| ----------------------- | ------------------------------------------------------- |
| `npm run dev`           | Dev server on port 3000                                 |
| `npm run build`         | Production build to `dist/` (no source maps)            |
| `npm run analyze`       | Build with the bundle visualizer, `dist/stats.html`     |
| `npm run lint`          | ESLint over the TypeScript source                       |
| `npm run typecheck`     | `tsc --noEmit`, app and build config                    |
| `npm test`              | Vitest (all tests)                                      |
| `npm run test:coverage` | Coverage report against the `vite.config.ts` thresholds |
| `npm run format`        | Prettier format                                         |
| `npm run format:check`  | Prettier check                                          |

### Backend commands

Run from the repository root, not from `backend/` — the tests need
`PYTHONPATH=backend/src` and pytest's config lives at the root.

| Command                                                  | Description                                  |
| -------------------------------------------------------- | -------------------------------------------- |
| `PYTHONPATH=backend/src pytest tests/backend/unit -v`    | Unit tests, coverage on, 80% floor           |
| `PYTHONPATH=backend/src pytest <one file> -v --no-cov`   | One file (`--no-cov`, or the floor fails it) |
| `ruff check backend/src/ tests/ backend/scripts/`        | Lint                                         |
| `ruff format --check backend/src/`                       | Format check (source only, deliberately)     |
| `mypy --config-file backend/pyproject.toml backend/src/` | Types                                        |
| `sam local start-api`                                    | Local API (set `GENERATE_ASYNC=false`)       |

### E2E tests (MiniStack)

```bash
make e2e-up      # Start MiniStack (Docker)
make e2e         # Run the E2E suite with the environment CI gives it
make e2e-down    # Stop MiniStack
```

## Project Structure

```text
├── frontend/               # React + Vite + TypeScript
│   ├── src/
│   │   ├── components/     # UI by domain: admin, common, errors, gallery,
│   │   │                   #   gating, generation, layout, tier
│   │   ├── pages/          # Route-level views (Admin, AuthCallback, Billing*)
│   │   ├── hooks/          # Six hooks (session polling, iteration, gallery,
│   │   │                   #   /me polling, breakpoint, sound)
│   │   ├── stores/         # Six Zustand stores (app, UI, toast, auth,
│   │   │                   #   billing, admin)
│   │   ├── api/            # API client, config, Cognito, billing, admin
│   │   └── types/          # TypeScript types
│   └── tests/              # Vitest + React Testing Library
├── backend/
│   ├── scripts/deploy.js   # `npm run deploy` — the live deploy entrypoint
│   ├── template.yaml       # SAM: Lambda, HttpApi, S3, CloudFront, DynamoDB,
│   │                       #   Cognito, alarms, the EventBridge schedule
│   └── src/
│       ├── lambda_function.py  # Every route, plus two non-HTTP entry paths
│       ├── config.py           # 4 fixed model configs + all env vars
│       ├── admin/              # Admin API: users, models, metrics, revenue
│       ├── api/                # Prompt enhancement, logging, pricing
│       ├── auth/               # JWT claims, HMAC-signed guest tokens
│       ├── billing/            # Stripe checkout, portal, webhook
│       ├── jobs/               # SessionManager (S3 state, ETag-conditional)
│       ├── models/             # Provider handlers + iteration context
│       ├── notifications/      # SES email sender and templates
│       ├── ops/                # Spend metering, model caps, CAPTCHA,
│       │                       #   CloudWatch metrics, store circuit breaker
│       ├── prompts/            # Prompt history and the public recent feed
│       ├── users/              # Tier resolution, quota, DynamoDB repository
│       └── utils/              # clients, content_filter, error_responses,
│                               #   http, logger, outpaint, retry, storage
├── tests/
│   └── backend/
│       ├── unit/           # Unit tests (moto S3/DynamoDB mocks)
│       └── e2e/            # E2E tests (MiniStack)
├── docs/adr/               # Architecture Decision Records
├── docker-compose.yml      # MiniStack for E2E tests
├── Makefile                # Common dev commands; CI invokes these targets
└── CONTRIBUTING.md         # Contribution guide
```

The seven packages under `backend/src/` that hold auth, money and quotas —
`admin/`, `auth/`, `billing/`, `notifications/`, `ops/`, `prompts/`, `users/` —
are where most of the behaviour that is not image generation lives.

## AI Models

Four fixed models run in parallel for every generation:

| Name        | Provider       | Default Model ID               | Enable Env Var    |
| ----------- | -------------- | ------------------------------ | ----------------- |
| Gemini      | Google         | gemini-3.1-flash-image-preview | `GEMINI_ENABLED`  |
| Nova Canvas | Amazon Bedrock | amazon.nova-canvas-v1:0        | `NOVA_ENABLED`    |
| DALL-E 3    | OpenAI         | dall-e-3                       | `OPENAI_ENABLED`  |
| Firefly     | Adobe          | firefly-image-5                | `FIREFLY_ENABLED` |

Each model requires its own credentials. Gemini and OpenAI need API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`). Firefly uses OAuth2 (`FIREFLY_CLIENT_ID`, `FIREFLY_CLIENT_SECRET`). Nova Canvas uses the Lambda IAM role (no API key). Models can be individually disabled.

## Troubleshooting

**Python version mismatch**
This project requires Python 3.13+. Check with `python3 --version`. If using pyenv: `pyenv install 3.13` and `pyenv local 3.13`.

**Frontend port conflict**
The dev server runs on port 3000 (`vite.config.ts`). If the port is taken, Vite will fail with `EADDRINUSE`. Kill the conflicting process or temporarily edit `vite.config.ts`.

**Backend tests fail with import errors**
Always run backend tests from the repository root with the
`PYTHONPATH=backend/src` prefix. Nothing sets it for you — no conftest touches
`sys.path`; CI sets it as job environment. `make test-backend` sets it too.

**SAM deploy fails on first run**
Use `sam deploy --guided` for the initial deployment to create `samconfig.toml`. Subsequent deploys use `sam deploy`.

**Every request fails, with nothing in the handler logs**
The Lambda is raising during initialisation, so no handler runs and there is no
request to attach the error to — look at the function's init logs. The usual
cause is `AUTH_ENABLED` unset, which is mandatory and has no default. The other
is `CREDITS_ENABLED=true` with any credit value set to zero or negative, which
also raises at import. Both messages name the variable.

**A single backend test file reports ~10% coverage and exits 1**
Coverage is on by default (`pytest.ini`) with an 80% floor (`.coveragerc`), and
one file cannot reach it. Add `--no-cov`; the tests still run and report.

**Models return errors in local dev**
Each model needs its credentials. Check `backend/.env.example` for required env vars per model. Models can be individually disabled (e.g., `NOVA_ENABLED=false`).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow, coding standards, and PR process.

## Reference

[CLAUDE.md](CLAUDE.md) is the deep reference for both humans and AI assistants:
the full endpoint table, the module tree, every environment variable with its
default, the session lifecycle and the S3 visibility model.

## License

[Apache 2.0](LICENSE)
