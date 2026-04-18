<div align="center">
<h1>Pixel Prompt Complete</h1>

[![CI](https://github.com/HatmanStack/pixel-prompt-complete/actions/workflows/ci.yml/badge.svg)](https://github.com/HatmanStack/pixel-prompt-complete/actions/workflows/ci.yml)
<a href="https://www.apache.org/licenses/LICENSE-2.0.html"><img src="https://img.shields.io/badge/license-Apache2.0-blue" alt="Apache 2.0 license" /></a>
<a href="https://reactjs.org/"><img src="https://img.shields.io/badge/React-19-61DAFB" alt="React 19" /></a>
<a href="https://aws.amazon.com/lambda/"><img src="https://img.shields.io/badge/AWS-Lambda-FF9900" alt="AWS Lambda" /></a>
<a href="https://docs.aws.amazon.com/serverless-application-model/"><img src="https://img.shields.io/badge/AWS-SAM-FF9900" alt="AWS SAM" /></a>

<p><b>Serverless text-to-image generation with parallel AI model execution</b></p>
<p><a href="https://production.d2iujulgl0aoba.amplifyapp.com/">Live Demo</a></p>

** THIS REPO IS IN ACTIVE DEVELOPMENT AND WILL CHANGE OFTEN **
</div>

## What is this?

Pixel Prompt is a serverless platform that generates images from text prompts using four AI models simultaneously. Submit a prompt, get results from Gemini, Nova Canvas, DALL-E 3, and Firefly side-by-side, then iterate on any model's output with follow-up prompts or expand images to different aspect ratios. Deployed on AWS with Lambda, S3, and CloudFront — no servers to manage.

## Architecture

```
                          ┌──────────────┐
                          │  React App   │
                          │  (Vite/TS)   │
                          └──────┬───────┘
                                 │
                          ┌──────▼───────┐
                          │ API Gateway  │
                          │   (HttpApi)  │
                          └──────┬───────┘
                                 │
                          ┌──────▼───────┐
                          │   Lambda     │
                          │  (Python)    │
                          └──────┬───────┘
                                 │
              ┌─────────────────────────────────────────────┐
              │       ThreadPoolExecutor (4 workers)         │
              ├──────────┬──────────┬───────────┬────────────┤
              │  Gemini  │  Nova    │  DALL-E 3 │  Firefly   │
              │ (Google) │ (AWS)    │ (OpenAI)  │  (Adobe)   │
              └──────────┴──────┬───┴───────────┴────────────┘
                                │
                         ┌──────▼───────┐
                         │      S3      │
                         │  (sessions)  │
                         └──────┬───────┘
                                │
                         ┌──────▼───────┐
                         │  CloudFront  │
                         │    (CDN)     │
                         └──────────────┘
```

## Quick Start (Frontend Only)

```bash
git clone https://github.com/HatmanStack/pixel-prompt-complete.git
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
- **AWS CLI** configured (`aws configure`)
- **AWS SAM CLI** for serverless deployment

### Deploy Backend

```bash
cd backend
sam build
sam deploy --guided   # First-time: configures models, API keys, rate limits
```

Configuration saved to `samconfig.toml`. Subsequent deploys: `sam build && sam deploy`.

### Run Frontend

```bash
cd frontend
npm install
npm run dev
```

## Development

### Frontend Commands

| Command | Description |
|---------|-------------|
| `npm run dev` | Dev server on port 3000 |
| `npm run build` | Production build |
| `npm run lint` | ESLint |
| `npm run typecheck` | TypeScript check |
| `npm test` | Vitest (all tests) |
| `npm run test:coverage` | Coverage report |
| `npm run format` | Prettier format |
| `npm run format:check` | Prettier check |

### Backend Commands

| Command | Description |
|---------|-------------|
| `PYTHONPATH=backend/src pytest tests/backend/unit -v` | Unit tests |
| `ruff check backend/src/` | Lint |
| `ruff format backend/src/` | Format |
| `sam local start-api` | Local API |

### E2E Tests (MiniStack)

```bash
make e2e-up                                    # Start MiniStack
PYTHONPATH=backend/src pytest tests/backend/e2e -v -m e2e  # Run E2E
make e2e-down                                  # Stop MiniStack
```

### Quick Check (All Tests + Linting)

```bash
make check
```

## Project Structure

```
├── frontend/               # React + Vite + TypeScript
│   ├── src/
│   │   ├── components/     # UI components (layout, generation, gallery)
│   │   ├── hooks/          # Custom hooks (polling, iteration, gallery)
│   │   ├── stores/         # Zustand state (app, UI, toast)
│   │   ├── api/            # API client
│   │   └── types/          # TypeScript types
│   └── tests/              # Vitest + React Testing Library
├── backend/
│   └── src/
│       ├── lambda_function.py  # Main handler — routes all endpoints
│       ├── config.py           # 4 fixed model configs + env vars
│       ├── models/             # Handlers (generate, iterate, outpaint)
│       ├── jobs/               # SessionManager (S3-based state)
│       ├── api/                # Prompt enhancement, logging
│       └── utils/              # Storage, rate limiting, content filter
├── tests/
│   └── backend/
│       ├── unit/           # Unit tests (moto S3 mocks)
│       └── e2e/            # E2E tests (MiniStack)
├── docs/adr/               # Architecture Decision Records
├── docker-compose.yml      # MiniStack for E2E tests
├── Makefile                # Common dev commands
└── CONTRIBUTING.md         # Contribution guide
```

## AI Models

Four fixed models run in parallel for every generation:

| Name | Provider | Default Model ID | Enable Env Var |
|------|----------|-------------------|----------------|
| Gemini | Google | gemini-3.1-flash-image-preview | `GEMINI_ENABLED` |
| Nova Canvas | Amazon Bedrock | amazon.nova-canvas-v1:0 | `NOVA_ENABLED` |
| DALL-E 3 | OpenAI | dall-e-3 | `OPENAI_ENABLED` |
| Firefly | Adobe | firefly-image-5 | `FIREFLY_ENABLED` |

Each model requires its own credentials. Gemini and OpenAI need API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`). Firefly uses OAuth2 (`FIREFLY_CLIENT_ID`, `FIREFLY_CLIENT_SECRET`). Nova Canvas uses the Lambda IAM role (no API key). Models can be individually disabled.

## Troubleshooting

**Python version mismatch**
This project requires Python 3.13+. Check with `python3 --version`. If using pyenv: `pyenv install 3.13` and `pyenv local 3.13`.

**Frontend port conflict**
The dev server runs on port 3000 (`vite.config.ts`). If the port is taken, Vite will fail with `EADDRINUSE`. Kill the conflicting process or temporarily edit `vite.config.ts`.

**Backend tests fail with import errors**
Always run backend tests with `PYTHONPATH=backend/src` prefix. The test conftest adds this automatically in CI but not locally.

**SAM deploy fails on first run**
Use `sam deploy --guided` for the initial deployment to create `samconfig.toml`. Subsequent deploys use `sam deploy`.

**Models return errors in local dev**
Each model needs its credentials. Check `backend/.env.example` for required env vars per model. Models can be individually disabled (e.g., `NOVA_ENABLED=false`).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow, coding standards, and PR process.

## For AI Assistants

See [CLAUDE.md](CLAUDE.md) for detailed architecture context, API endpoints, and module structure.

## License

[Apache 2.0](LICENSE)
