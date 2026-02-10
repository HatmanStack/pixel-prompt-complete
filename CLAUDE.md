# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pixel Prompt v2 is a serverless text-to-image generation platform with iterative refinement. Built with AWS Lambda (Python 3.13) and React (TypeScript, Vite). Supports 4 fixed AI models (Flux, Recraft, Gemini, OpenAI) running in parallel, with per-model iteration and outpainting.

**Request Flow**: User prompt → API Gateway (HttpApi) → Lambda → ThreadPoolExecutor generates images across enabled models → Results stored in S3 → CloudFront CDN delivery. Users can then iterate on individual model results or outpaint to different aspect ratios.

## Essential Commands

### Frontend (React + Vite + TypeScript)

```bash
cd frontend
npm install
npm run dev              # Dev server
npm run build            # Production build to dist/
npm run lint             # ESLint (flat config)
npm run typecheck        # tsc --noEmit
npm test                 # Vitest (all tests)
npm test -- <file-path>  # Single test file
npm run test:coverage    # Coverage report
npm run test:watch       # Watch mode
```

### Backend (Python 3.13, AWS SAM)

```bash
cd backend
sam build
sam deploy               # Uses samconfig.toml
sam deploy --guided      # First-time interactive deploy

# Tests run from repo root (PYTHONPATH must include backend/src)
PYTHONPATH=backend/src pytest tests/backend/unit/ -v
PYTHONPATH=backend/src pytest tests/backend/unit/test_handlers.py -v  # Single file

# Linting
ruff check backend/src/

# Local Lambda testing
sam local invoke -e events/generate.json
sam local start-api
```

### CI (`.github/workflows/ci.yml`)

Runs on push/PR to main/develop: frontend lint + typecheck → frontend tests → backend lint + tests. Backend CI sets `PYTHONPATH=$GITHUB_WORKSPACE/backend/src`.

## Architecture

### Backend Module Structure

```
backend/src/
├── lambda_function.py       # Main handler - routes all API endpoints
├── config.py                # 4 fixed ModelConfig dataclasses + env var loading
├── models/
│   ├── registry.py          # ModelRegistry (legacy, still present)
│   ├── handlers.py          # 3 handler types per provider: generate, iterate, outpaint
│   └── context.py           # ContextManager: rolling 3-iteration window per model in S3
├── jobs/
│   └── manager.py           # SessionManager: S3-based session state with optimistic locking
├── api/
│   ├── enhance.py           # PromptEnhancer: LLM-based prompt improvement
│   └── log.py               # Client-side logging endpoint
└── utils/
    ├── storage.py           # ImageStorage: S3 upload, CloudFront URLs, gallery listing
    ├── rate_limit.py        # RateLimiter: Global hourly + per-IP daily, S3-backed
    ├── content_filter.py    # ContentFilter: keyword-based pre-filtering
    ├── error_responses.py   # Standardized error response factories
    ├── retry.py             # Exponential backoff decorator
    ├── outpaint.py          # Outpaint utility functions
    └── logger.py            # StructuredLogger: JSON CloudWatch logs
```

### API Endpoints

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| POST | /generate | `handle_generate` | Create session, generate initial images for all enabled models |
| POST | /iterate | `handle_iterate` | Refine one model's image with new prompt (needs sessionId + model) |
| POST | /outpaint | `handle_outpaint` | Expand image to new aspect ratio (presets: 16:9, 9:16, 1:1, 4:3, expand_all) |
| GET | /status/{sessionId} | `handle_status` | Get session state with all model iterations |
| POST | /enhance | `handle_enhance` | LLM prompt improvement |
| GET | /gallery/list | `handle_gallery_list` | List galleries with preview thumbnails |
| GET | /gallery/{sessionId} | `handle_gallery_detail` | Get all images from a gallery |
| POST | /log | `handle_log_endpoint` | Client error logging |

### Model Configuration (Fixed 4 Models)

Configured via `config.py` dataclasses with enable/disable flags. **Not dynamic** — always exactly these 4:

| Config Name | Provider | Default Model ID | Env Vars |
|-------------|----------|-------------------|----------|
| flux | bfl | flux-2-pro | `FLUX_ENABLED`, `FLUX_API_KEY`, `FLUX_MODEL_ID` |
| recraft | recraft | recraftv3 | `RECRAFT_ENABLED`, `RECRAFT_API_KEY`, `RECRAFT_MODEL_ID` |
| gemini | google_gemini | gemini-2.5-flash-image | `GEMINI_ENABLED`, `GEMINI_API_KEY`, `GEMINI_MODEL_ID` |
| openai | openai | gpt-image-1 | `OPENAI_ENABLED`, `OPENAI_API_KEY`, `OPENAI_MODEL_ID` |

Prompt enhancement uses separate config: `PROMPT_MODEL_PROVIDER`, `PROMPT_MODEL_ID`, `PROMPT_MODEL_API_KEY`.

### Handler System

`handlers.py` has **three handler types** per provider, registered in factory functions:

- **`get_handler(provider)`** → `handle_<provider>(config, prompt, params)` — Initial generation
- **`get_iterate_handler(provider)`** → `iterate_<provider>(config, source_image, prompt, context)` — Iterative refinement with context
- **`get_outpaint_handler(provider)`** → `outpaint_<provider>(config, source_image, preset, prompt)` — Aspect ratio expansion

All return `{'status': 'success', 'image': base64_str, ...}` or `{'status': 'error', 'error': msg, ...}`.

### Session Lifecycle

1. **POST /generate** → `SessionManager.create_session()` creates `sessions/{sessionId}/status.json` in S3
2. `ThreadPoolExecutor(max_workers=4)` runs all enabled models in parallel
3. Each model: get handler → generate → upload to S3 → `complete_iteration()` with optimistic locking (version field)
4. **POST /iterate** → Loads source image from latest iteration → gets rolling 3-entry context from `ContextManager` → calls iterate handler → stores new iteration
5. **POST /outpaint** → Similar to iterate but uses outpaint handler with aspect ratio preset
6. Max 7 iterations per model per session (`MAX_ITERATIONS` in config.py)

**S3 Structure**:
```
sessions/{sessionId}/status.json           # Session metadata + iteration array per model
sessions/{sessionId}/context/{model}.json  # Rolling 3-iteration context window
gallery/{timestamp}/                       # Gallery images with metadata
```

### Frontend Architecture

TypeScript React app using **Zustand** for state management (not Context API).

**State Stores** (`stores/`):
- `useAppStore` — Session state, results, prompt, generation status
- `useUIStore` — UI state (modals, panels, view mode)
- `useToastStore` — Toast notification queue

**Key Hooks**:
- `useSessionPolling` / `useJobPolling` — Poll /status/{sessionId} until complete
- `useIteration` — Manage per-model iteration workflow
- `useGallery` — Fetch gallery list
- `useBreakpoint` — Responsive breakpoint detection
- `useSound` — Sound effects

**Layout**: `ResponsiveLayout` → `DesktopLayout` (4-column model grid) or `MobileLayout`. Each model gets a `ModelColumn` with `IterationCard` entries and `IterationInput` for refinement.

## Test Structure

Tests live at repo root in `tests/` (not inside `backend/` or `frontend/`):

```
tests/backend/unit/          # Unit tests with moto S3 mocks (conftest.py provides mock_s3 fixture)
tests/backend/unit/fixtures/ # Shared API response fixtures
tests/backend/integration/   # Integration tests (require deployed backend + API_ENDPOINT env var)
frontend/tests/__tests__/    # Vitest + React Testing Library
  components/                # Component tests (.jsx and .tsx)
  hooks/                     # Hook tests
  stores/                    # Zustand store tests
  integration/               # Integration tests
  utils/                     # Utility tests
```

## Adding a New Handler Type for Existing Provider

Each provider needs 3 handlers. If adding iteration support to a provider that only has generation:

1. Add `iterate_<provider>()` function in `handlers.py` matching `IterateHandlerFunc` signature
2. Register in `get_iterate_handler()` dict
3. Add tests in `tests/backend/unit/test_iterate_handlers.py`

Same pattern for outpaint: add `outpaint_<provider>()`, register in `get_outpaint_handler()`.

## Important Constraints

- **Lambda**: 900s timeout, 3008 MB memory, 10 reserved concurrent executions
- **S3 Lifecycle**: Sessions auto-deleted after 30 days
- **Iteration Limit**: 7 per model per session (configurable via `MAX_ITERATIONS`)
- **Context Window**: Rolling 3 iterations maintained per model
- **Session Locking**: Optimistic locking via version field in status.json (3 retries)
- **API Throttling**: 50 req/s steady, 100 burst (HttpApi DefaultRouteSettings)
- **Python Runtime**: 3.13 (pyproject.toml target, template.yaml runtime)
- **Ruff Config**: `pyproject.toml` — line-length 100, rules E/F/W/I, ignore E501
- **Frontend**: React 19, Zustand 5, Tailwind CSS 4, Vite 7, Vitest 1

## Repository Context

This is a **submodule** of the parent `pixel-prompt` repository. This "complete" variant is the full-stack AWS serverless implementation.
