# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pixel Prompt Complete is a serverless text-to-image generation platform that supports parallel execution across multiple AI models. Built with AWS Lambda (Python 3.12 backend) and React (Vite frontend).

**Key Architecture**: User submits prompt → API Gateway → Lambda executes async jobs → Multiple AI providers generate images in parallel → Results stored in S3 → CloudFront CDN delivery

## Essential Commands

### Backend (AWS SAM)

```bash
# Build Lambda function
cd backend && sam build

# Deploy (first time - interactive)
sam deploy --guided

# Deploy (subsequent - uses samconfig.toml)
sam deploy

# Deploy to specific environment
sam deploy --config-env dev|staging|prod

# Local testing
sam local invoke -e events/generate.json
sam local start-api

# View logs
sam logs --stack-name <stack-name> --tail

# Get stack outputs (API endpoint, CloudFront domain)
sam list stack-outputs --stack-name <stack-name>
```

### Frontend (React + Vite)

```bash
cd frontend

# Development
npm install
npm run dev          # Start dev server on port 3000

# Production build
npm run build        # Output to dist/
npm run preview      # Preview production build

# Linting
npm run lint

# Testing
npm test                    # Run all tests
npm test -- --watch         # Watch mode
npm run test:ui             # Interactive UI
npm run test:coverage       # Coverage report
npm test -- <file-path>     # Run specific test file
```

### Backend Testing

```bash
cd backend

# Install dependencies
pip install -r requirements.txt -r tests/requirements.txt

# Unit tests (88 tests)
pytest tests/unit/ -v

# Specific test file
pytest tests/unit/test_content_filter.py -v

# Coverage
pytest tests/unit/ --cov=src --cov-report=html
open htmlcov/index.html

# Integration tests (requires deployed backend)
export API_ENDPOINT="https://..."
pytest tests/integration/ -v
```

### Deployment Scripts

```bash
# Full backend deployment (build + deploy + configure frontend)
./scripts/deploy.sh dev|staging|prod

# Automated benchmarking
./scripts/benchmark-lambda.sh <api-endpoint>

# Load testing
./scripts/run-loadtest.sh <api-endpoint>

# CloudFront testing
./scripts/test-cloudfront.sh <api-endpoint>

# Frontend performance audit
./scripts/lighthouse-audit.sh <frontend-url>
```

## Architecture Deep Dive

### Backend Module Structure

**Critical Flow**: `lambda_function.py` routes requests → `jobs/manager.py` creates jobs → `jobs/executor.py` spawns threads → `models/handlers.py` calls AI APIs → `utils/storage.py` uploads to S3

```
backend/src/
├── lambda_function.py       # Main handler - routes /generate, /status, /enhance
├── config.py                # Env vars → MODEL_COUNT, MODEL_1_NAME, MODEL_1_KEY, etc.
├── models/
│   ├── registry.py          # ModelRegistry: 1-based indexing, provider detection
│   └── handlers.py          # Provider handlers: OpenAI, Google, Bedrock, BFL, Recraft
├── jobs/
│   ├── manager.py           # JobManager: S3-based job state (status.json)
│   └── executor.py          # JobExecutor: Parallel threading, error isolation
├── api/
│   ├── enhance.py           # PromptEnhancer: LLM prompt improvement
│   └── log.py               # Client-side logging endpoint
└── utils/
    ├── storage.py           # ImageStorage: S3 upload, CloudFront URLs
    ├── rate_limit.py        # RateLimiter: Global + per-IP tracking
    ├── content_filter.py    # ContentFilter: NSFW detection
    ├── retry.py             # Exponential backoff decorator
    └── logger.py            # StructuredLogger: JSON CloudWatch logs
```

### Model Configuration System

**Critical**: The backend uses **1-based indexing** for models (MODEL_1, MODEL_2...) but Python internals use 0-based arrays.

Models configured via CloudFormation parameters:
- `ModelCount`: 1-20 (number of active models)
- `Model{1-20}Name`: Display name (e.g., "DALL-E 3", "Gemini 2.0")
- `Model{1-20}Key`: API key (NoEcho: true)
- `PromptModelIndex`: Which model handles /enhance (1-based)

**Provider Detection** (`models/registry.py`): Model names are pattern-matched to determine provider:
- "DALL-E" / "dalle" → OpenAI handler
- "Gemini" / "gemini" → Google Gemini handler
- "Imagen" / "imagen" → Google Imagen handler
- "Nova Canvas" → AWS Bedrock Nova
- "Stable Diffusion 3.5" → AWS Bedrock SD3.5
- "Black Forest" / "Flux" → BFL API
- "Recraft" → Recraft API
- "Stability" → Stability AI API

### Job Lifecycle

1. **POST /generate** → Creates job with UUID, stores `status.json` in S3
2. **JobExecutor.execute_job()** → Spawns thread per model
3. Each thread: Call provider → Upload image → Update job status atomically
4. **GET /status/{jobId}** → Returns aggregated results from `status.json`

**Key S3 Structure**:
```
s3://bucket/
├── group-images/{jobId}/
│   ├── status.json          # Job metadata, results array
│   ├── model1-result.png
│   ├── model2-result.png
│   └── ...
└── gallery/{timestamp}/
    └── status.json          # Gallery index
```

### Frontend Architecture

**Critical Pattern**: Dynamic model support - frontend adapts to backend's MODEL_COUNT without hardcoding model names.

```
frontend/src/
├── api/
│   ├── client.js            # Fetch wrapper, correlation IDs, retries
│   └── config.js            # VITE_API_ENDPOINT env var
├── components/
│   ├── generation/
│   │   ├── PromptInput.jsx         # Main text input
│   │   ├── ParameterSliders.jsx    # steps, guidance, control
│   │   ├── GenerateButton.jsx      # Submit + job polling
│   │   ├── ImageGrid.jsx           # Progressive result display
│   │   └── ImageCard.jsx           # Individual result + modal
│   ├── gallery/
│   │   ├── GalleryBrowser.jsx      # Historical generations
│   │   └── GalleryPreview.jsx      # Thumbnail grid
│   └── common/                      # Reusable UI components
├── hooks/
│   ├── useJobPolling.js     # Poll /status every 2s until complete
│   ├── useGallery.js        # Fetch /gallery/list
│   └── useImageLoader.js    # Progressive image loading
└── context/
    └── AppContext.jsx       # Global state: jobId, results, errors
```

**Job Polling Pattern** (`hooks/useJobPolling.js`):
- Starts when jobId received from /generate
- Polls /status/{jobId} every 2 seconds
- Updates UI progressively as each model completes
- Stops when status === "completed" or "failed"

### Rate Limiting System

Two-tier rate limiting stored in S3 (`rate-limits/` prefix):
- **Global**: `global_counter.json` - hourly request count
- **Per-IP**: `ip_{hash}.json` - daily request count per IP

Whitelisted IPs (comma-separated in `IPWhitelist` parameter) bypass all limits.

### Content Filtering

`ContentFilter` uses keyword matching + client-side pre-filtering. Not comprehensive - relies on AI provider's built-in NSFW detection as primary defense.

## Configuration & Secrets

### Backend Environment Variables (set via SAM parameters)

Required for each model:
- `MODEL_1_NAME` through `MODEL_20_NAME`
- `MODEL_1_KEY` through `MODEL_20_KEY`

AWS Bedrock models (Nova Canvas, SD3.5):
- Use AWS credentials from Lambda execution role
- Set `MODEL_X_KEY` to `"N/A"` for Bedrock models
- Ensure Lambda role has `bedrock-runtime:InvokeModel` permissions

### Frontend Environment Variables

Create `frontend/.env`:
```bash
VITE_API_ENDPOINT=https://xxxx.execute-api.region.amazonaws.com/Prod
```

## Testing Philosophy

**Backend**: 88 unit tests with mocked S3/APIs + integration tests against live deployment
**Frontend**: 122 component tests + 23 integration tests using Vitest + React Testing Library

**Critical Testing Pattern**: Always test error isolation in parallel execution - one model failure should not crash entire job.

## Common Development Workflows

### Adding a New AI Provider

1. Add handler class to `backend/src/models/handlers.py`:
   ```python
   class NewProviderHandler(BaseHandler):
       def generate_image(self, prompt, **params):
           # Implementation
   ```

2. Add provider detection in `backend/src/models/registry.py`:
   ```python
   if "provider-keyword" in model_name.lower():
       return NewProviderHandler(model_name, api_key)
   ```

3. Add unit tests in `backend/tests/unit/test_handlers.py`

4. Deploy with model configured:
   ```bash
   sam deploy --parameter-overrides Model1Name="Provider Name" Model1Key="api-key"
   ```

### Modifying Job Schema

Job status schema in `jobs/manager.py` defines S3 `status.json` structure. Changes require:
1. Update `create_job()` and `get_job_status()` in `JobManager`
2. Update frontend polling in `hooks/useJobPolling.js`
3. Test with integration tests

### Debugging Lambda Locally

```bash
# Create test event file
cat > events/test.json <<EOF
{
  "httpMethod": "POST",
  "path": "/generate",
  "body": "{\"prompt\":\"test\",\"ip\":\"127.0.0.1\"}"
}
EOF

# Invoke locally
sam local invoke -e events/test.json

# Or start local API
sam local start-api
curl -X POST http://localhost:3000/generate -d '{"prompt":"test","ip":"127.0.0.1"}'
```

## GitHub Actions Workflows

Located in `.github/workflows/`:
- **test.yml**: Runs on PR/push - frontend & backend tests + linting
- **deploy-staging.yml**: Auto-deploys to staging on main branch push
- **deploy-production.yml**: Manual production deployment with confirmation

## Important Constraints

1. **Lambda Timeout**: 900s (15 minutes) - longest model must complete within this
2. **Lambda Memory**: 3008 MB - required for concurrent provider SDK usage
3. **S3 Lifecycle**: Images auto-deleted after 30 days (configurable in template.yaml)
4. **CloudFront Deployment**: Takes 10-15 minutes - don't test images immediately after deploy
5. **Model Indexing**: Always 1-based in parameters, 0-based internally in Python
6. **API Gateway Throttling**: 50 req/s steady, 100 burst (configurable in template.yaml)

## Troubleshooting Quick Reference

**"Images not displaying"**: CloudFront distribution still deploying (wait 15 min) or check S3 bucket policy allows OAI access

**"Rate limit exceeded"**: Check `rate-limits/` objects in S3, verify IP whitelist, or adjust `GlobalRateLimit`/`IPRateLimit` parameters

**"Model X failed"**: Check CloudWatch logs for API key validity, quota limits, or regional availability (Bedrock models are region-specific)

**"Job stuck in progress"**: Lambda timeout or thread deadlock - check CloudWatch for errors, verify provider API responsiveness

**Frontend can't connect**: Verify CORS in API Gateway (should allow `*` origin), check `frontend/.env` has correct endpoint

## Repository Structure Notes

This is a **submodule** of the main `pixel-prompt` repository. Parent repo contains other implementation variants (container, JS, frontend-only, etc.). This "complete" variant is the full-stack AWS serverless implementation.
