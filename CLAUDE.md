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
├── config.py                # Env vars → MODEL_COUNT, MODEL_{N}_PROVIDER/ID/API_KEY/BASE_URL/USER_ID
├── models/
│   ├── registry.py          # ModelRegistry: 1-based indexing, explicit provider config
│   └── handlers.py          # Provider handlers: OpenAI, Google, Bedrock, BFL, Recraft, get_handler() factory
├── jobs/
│   ├── manager.py           # JobManager: S3-based job state (status.json)
│   └── executor.py          # JobExecutor: Parallel threading (ThreadPoolExecutor), error isolation
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

Models configured via CloudFormation parameters using **5-field format**:
- `ModelCount`: 1-20 (number of active models)
- `PromptModelIndex`: Which model handles /enhance (1-based)

**For each model (1-20):**
- `Model{N}Provider`: **Required** - Explicit provider type (e.g., "openai", "google_gemini", "bedrock_nova", "bfl", "recraft", "stability", "generic")
- `Model{N}Id`: **Required** - Model identifier for API calls (e.g., "dall-e-3", "gemini-2.0-flash-exp", "flux-pro-1.1")
- `Model{N}ApiKey`: *Optional* - API key (NoEcho: true, not needed for Bedrock)
- `Model{N}BaseUrl`: *Optional* - Custom API endpoint (for OpenAI-compatible APIs)
- `Model{N}UserId`: *Optional* - User identifier (if provider requires it)

**Important**: Empty optional fields are NOT sent to providers - only non-empty values are included in API calls (`config.py:45-50`).

**Provider Types** (explicit specification, no pattern matching):
- `openai` - OpenAI DALL-E models
- `google_gemini` - Google Gemini image generation
- `google_imagen` - Google Imagen models
- `bedrock_nova` - AWS Bedrock Nova Canvas (uses Lambda IAM role, no API key needed)
- `bedrock_sd` - AWS Bedrock Stable Diffusion 3.5 (uses Lambda IAM role)
- `bfl` - Black Forest Labs (Flux models)
- `recraft` - Recraft v3
- `stability` - Stability AI models
- `generic` - OpenAI-compatible APIs (requires BaseUrl)

### Job Lifecycle

1. **POST /generate** → Creates job with UUID, stores `status.json` in S3
2. **JobExecutor.execute_job()** → Spawns thread per model (ThreadPoolExecutor, max 10 workers)
3. Each thread (`_execute_model()`):
   - Gets handler function: `handler = get_handler(model['provider'])`
   - Calls handler: `result = handler(model_config, prompt, params)` (with 120s timeout)
   - If success: Upload image to S3, update job status
   - If error: Log error, update job status with error message
   - Error isolation: One model failure doesn't affect others
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

**5-field format for each model (1-20):**
- `MODEL_{N}_PROVIDER` - **Required**: Provider type (openai, google_gemini, bedrock_nova, etc.)
- `MODEL_{N}_ID` - **Required**: Model identifier (dall-e-3, flux-pro-1.1, etc.)
- `MODEL_{N}_API_KEY` - *Optional*: API key (leave empty for Bedrock models)
- `MODEL_{N}_BASE_URL` - *Optional*: Custom API endpoint
- `MODEL_{N}_USER_ID` - *Optional*: User identifier

**AWS Bedrock models** (Nova Canvas, SD3.5):
- Use AWS credentials from Lambda execution role (no API key needed)
- Leave `MODEL_{N}_API_KEY` empty (not "N/A", just empty string)
- Ensure Lambda role has `bedrock-runtime:InvokeModel` permissions

**Generic provider** (OpenAI-compatible APIs):
- Set `MODEL_{N}_PROVIDER` to `generic`
- `MODEL_{N}_BASE_URL` is **required** for generic provider
- Include API key in `MODEL_{N}_API_KEY` if needed

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

**Pattern**: Handlers are functions (not classes) that return standardized response dicts.

**Handler Contract**: All handlers must accept `(model_config: Dict, prompt: str, _params: Dict)` and return:
- Success: `{'status': 'success', 'image': base64_str, 'model': model_id, 'provider': provider_name}`
- Error: `{'status': 'error', 'error': error_message, 'model': model_id, 'provider': provider_name}`

1. Add handler function to `backend/src/models/handlers.py`:
   ```python
   def handle_new_provider(model_config: Dict, prompt: str, _params: Dict) -> Dict:
       """
       Handle image generation for NewProvider.

       Args:
           model_config: Dict with 'id', 'api_key', 'base_url', 'user_id' (optional fields)
           prompt: Text prompt for image generation
           _params: Generation parameters (steps, guidance, etc.)

       Returns:
           Dict with 'status', 'image' (base64), 'model', 'provider'
           OR 'status': 'error', 'error': message
       """
       try:
           # Initialize provider SDK
           api_key = model_config.get('api_key', '')
           model_id = model_config['id']

           # Call provider API
           # ... implementation ...

           # Return standardized success response
           return {
               'status': 'success',
               'image': base64_encoded_image,
               'model': model_id,
               'provider': 'new_provider'
           }
       except Exception as e:
           return {
               'status': 'error',
               'error': str(e),
               'model': model_config['id'],
               'provider': 'new_provider'
           }
   ```

2. Register handler in `get_handler()` dict in `backend/src/models/handlers.py` (around line 659):
   ```python
   handlers = {
       'openai': handle_openai,
       # ... existing handlers ...
       'new_provider': handle_new_provider,  # Add this line
   }
   ```

3. Add unit tests in `backend/tests/unit/test_handlers.py`

4. Update `template.yaml` if adding provider to allowed values (optional)

5. Deploy with explicit provider configuration:
   ```bash
   sam deploy --parameter-overrides \
     Model1Provider="new_provider" \
     Model1Id="model-identifier" \
     Model1ApiKey="api-key"
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

**"Prompt enhancement not working"**: Enhancement returns original prompt unchanged. See [DEBUGGING_ENHANCE.md](./DEBUGGING_ENHANCE.md) for detailed diagnostics. Quick checks:
- Run `./scripts/diagnose-enhance.sh <stack-name>` to check configuration
- Verify PROMPT_MODEL_INDEX is valid (1 to MODEL_COUNT)
- Check CloudWatch logs for `[ENHANCE]` errors: `sam logs --stack-name <stack-name> --tail --filter-pattern "[ENHANCE]"`
- Test endpoint: `./scripts/test-enhance-endpoint.sh <api-endpoint>`

## Repository Structure Notes

This is a **submodule** of the main `pixel-prompt` repository. Parent repo contains other implementation variants (container, JS, frontend-only, etc.). This "complete" variant is the full-stack AWS serverless implementation.
