# Phase 0: Foundation & Standards

## Phase Goal

Establish the architectural foundation, design decisions, deployment infrastructure, and testing patterns that all subsequent phases will build upon. This phase produces no user-visible features but creates the scaffolding for reliable, maintainable implementation.

**Success Criteria:**
- All Architecture Decision Records (ADRs) documented
- Deploy script specifications complete
- Testing strategy defined with mocking patterns
- Shared conventions established
- CI pipeline configuration updated

**Estimated Tokens:** ~15,000

## Prerequisites

- Access to the existing codebase
- Understanding of current architecture (20-model dynamic system)
- API documentation for all 4 target providers reviewed

---

## Architecture Decision Records (ADRs)

### ADR-001: Fixed 4-Model Architecture

**Status:** Accepted

**Context:**
The current system supports 1-20 dynamically configured models via CloudFormation parameters. This flexibility adds complexity to:
- SAM template (900+ lines of repetitive parameter definitions)
- Configuration management (20 model slots to track)
- Frontend UI (dynamic grid sizing)
- Error handling (variable model count edge cases)

**Decision:**
Lock the system to exactly 4 specific models:
1. **Flux** (Black Forest Labs) - `bfl` provider
2. **Recraft v3** - `recraft` provider
3. **Google Gemini** (Nano Banana) - `google_gemini` provider
4. **OpenAI gpt-image-1** - `openai` provider

Each model has:
- Fixed position (1-4)
- Enable/disable flag
- Version-swappable model ID
- Provider-specific API key

**Consequences:**
- (+) Drastically simplified SAM template (~200 lines vs 1300)
- (+) Predictable UI layout (always 4 columns)
- (+) Easier testing (known model set)
- (+) Provider-specific iteration handlers
- (-) Cannot add new providers without code changes
- (-) Must redeploy to add/remove models

**Alternatives Considered:**
- Keep dynamic system: Rejected due to complexity
- 3 models: Rejected; 4 provides good variety
- 6 models: Rejected; diminishing returns, increased cost

---

### ADR-002: Session-Based Storage Model

**Status:** Accepted

**Context:**
Current system uses job-based storage where each `/generate` call creates a job with results. For iterative refinement, we need to track:
- Original generation
- Up to 7 iterations per model
- Conversation context per model
- Relationships between images

**Decision:**
Replace job-centric storage with session-centric storage:

```
sessions/{sessionId}/
├── status.json           # Session metadata, prompt, timestamps
├── context/
│   ├── flux.json         # Flux conversation history (rolling 3)
│   ├── recraft.json      # Recraft conversation history
│   ├── gemini.json       # Gemini conversation history
│   └── openai.json       # OpenAI conversation history
└── images/
    ├── flux-0.png        # Flux original
    ├── flux-1.png        # Flux iteration 1
    ├── flux-2.png        # Flux iteration 2
    ├── recraft-0.png     # Recraft original
    └── ...
```

**Consequences:**
- (+) All related images grouped together
- (+) Context files support conversation continuity
- (+) Easy gallery grouping by session
- (+) Clean S3 lifecycle management (delete entire session)
- (-) Migration required from existing job structure
- (-) Slightly more complex status tracking

---

### ADR-003: Rolling Context Window (3 Iterations)

**Status:** Accepted

**Context:**
Conversational refinement requires sending context to the model. Options:
1. Full history: All prompts and images
2. Rolling window: Last N iterations
3. Parent-only: Just the previous iteration

**Decision:**
Use a rolling 3-iteration context window:
- Store last 3 (prompt, image) pairs per model
- Send all 3 when making iteration requests
- Older iterations available in UI but not in model context

**Rationale:**
- Google Gemini excels with multi-turn context
- OpenAI gpt-image-1 benefits from conversation history
- Flux and Recraft support image-to-image with prompt
- 3 iterations balances context richness vs token cost

**Context File Format:**
```json
{
  "model": "flux",
  "sessionId": "uuid",
  "window": [
    {
      "iteration": 5,
      "prompt": "make the sky more purple",
      "imageKey": "images/flux-5.png",
      "timestamp": "2025-01-15T10:30:00Z"
    },
    {
      "iteration": 6,
      "prompt": "add a rainbow",
      "imageKey": "images/flux-6.png",
      "timestamp": "2025-01-15T10:31:00Z"
    },
    {
      "iteration": 7,
      "prompt": "make it more vibrant",
      "imageKey": "images/flux-7.png",
      "timestamp": "2025-01-15T10:32:00Z"
    }
  ]
}
```

**Consequences:**
- (+) Reasonable context size for all providers
- (+) Predictable token costs
- (+) Simple window management (FIFO queue)
- (-) Context lost after 3 iterations
- (-) Users may need to re-describe desired changes

---

### ADR-004: Provider-Specific Iteration Strategies

**Status:** Accepted

**Context:**
Each provider has different image editing capabilities:
- **Flux**: FLUX.1 Fill (inpainting/outpainting with mask)
- **Recraft**: Image-to-image endpoint
- **Gemini**: Multi-turn conversation (send image + prompt)
- **OpenAI**: Edit endpoint (image + prompt, optional mask)

**Decision:**
Implement provider-specific `iterate()` methods that abstract differences:

| Provider | Iteration Method | Outpainting Method |
|----------|-----------------|-------------------|
| Flux | FLUX Fill with full-image mask | FLUX Fill with edge mask |
| Recraft | imageToImage endpoint | outpaint endpoint |
| Gemini | Multi-turn generate_content | Prompt-based ("extend...") |
| OpenAI | images.edit endpoint | images.edit with padded canvas |

**Handler Interface:**
```python
def iterate(model_config: Dict, source_image: bytes, prompt: str, context: List[Dict]) -> Dict:
    """
    Iterate on an existing image with a refinement prompt.

    Args:
        model_config: Provider credentials and settings
        source_image: Base64-encoded source image
        prompt: Refinement instruction
        context: Rolling 3-iteration context window

    Returns:
        {'status': 'success', 'image': base64_str, ...} or
        {'status': 'error', 'error': msg, ...}
    """

def outpaint(model_config: Dict, source_image: bytes, preset: str, prompt: str) -> Dict:
    """
    Expand image using aspect preset.

    Args:
        preset: '16:9', '9:16', '1:1', '4:3', or 'expand_all'
        prompt: Description for expanded regions
    """
```

**Consequences:**
- (+) Unified API for frontend
- (+) Leverage each provider's strengths
- (+) Can optimize per-provider
- (-) More complex handler code
- (-) Different quality/consistency per provider

---

### ADR-005: Unified Outpainting via Aspect Presets

**Status:** Accepted

**Context:**
Users want to expand images but shouldn't need to understand masks, padding, or provider-specific parameters.

**Decision:**
Provide 5 aspect presets that calculate expansion automatically:

| Preset | Target Ratio | Strategy |
|--------|-------------|----------|
| `16:9` | Landscape | Expand left/right to reach 16:9 |
| `9:16` | Portrait | Expand top/bottom to reach 9:16 |
| `1:1` | Square | Expand to make square |
| `4:3` | Standard | Expand to reach 4:3 |
| `expand_all` | +50% each side | Uniform expansion for cropping |

**Calculation Logic:**
```python
def calculate_expansion(current_width: int, current_height: int, preset: str) -> Dict:
    """
    Calculate pixel expansion needed for each edge.

    Returns:
        {
            'left': pixels_to_add,
            'right': pixels_to_add,
            'top': pixels_to_add,
            'bottom': pixels_to_add,
            'new_width': final_width,
            'new_height': final_height
        }
    """
```

**Provider Implementation:**
- **Flux**: Generate mask with transparent edges, use FLUX Fill
- **Recraft**: Use outpaint endpoint with direction params
- **Gemini**: Prompt: "Extend this image [direction] to show more of the scene"
- **OpenAI**: Pad canvas with transparency, use edit endpoint

**Consequences:**
- (+) Simple UI (5 buttons)
- (+) Consistent behavior across providers
- (+) No user math required
- (-) Less precise control than manual masking
- (-) Provider quality varies for outpainting

---

### ADR-006: Iteration Limits with Warning

**Status:** Accepted

**Context:**
Need to prevent runaway iteration chains while allowing creative exploration.

**Decision:**
- **Hard limit**: 7 iterations per model column
- **Warning**: Show warning at iteration 5 (3 remaining)
- **UI behavior**: Disable input after iteration 7

**Rationale:**
- 7 iterations provides substantial refinement opportunity
- Warning at 5 gives users time to save/export
- Prevents accidental cost accumulation
- Easy to increase limit later if needed

**Implementation:**
- Backend: Reject iteration requests beyond limit
- Frontend: Show warning toast at iteration 5
- Frontend: Hide/disable input at iteration 7

---

### ADR-007: Auto-Retry with Partial Results

**Status:** Accepted

**Context:**
Initial generation calls 4 providers in parallel. Some may fail due to:
- Rate limits
- API errors
- Timeout

**Decision:**
1. Execute all 4 models in parallel
2. If any fail, automatically retry once (with exponential backoff)
3. After retry, show partial results
4. Failed models display error state with "Retry" button

**Retry Logic:**
```python
async def execute_with_retry(model, prompt):
    try:
        return await execute_model(model, prompt)
    except Exception as e:
        await sleep(2)  # 2 second backoff
        try:
            return await execute_model(model, prompt)
        except Exception as e2:
            return {'status': 'error', 'error': str(e2)}
```

**Consequences:**
- (+) Better success rate (transient errors recovered)
- (+) Users see partial results immediately
- (+) Individual retry buttons for fine-grained control
- (-) Slightly longer initial generation (retry delay)
- (-) Complexity in error state management

---

## Deployment Script Specification

### Overview

The `npm run deploy` command executes `backend/scripts/deploy.js` which:
1. Checks prerequisites (AWS CLI, SAM CLI)
2. Loads/prompts for configuration
3. Validates configuration
4. Generates `samconfig.toml`
5. Runs `sam build && sam deploy`
6. Captures stack outputs
7. Updates `frontend/.env`

### Configuration Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT CONFIGURATION                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Check for .deploy-config.json (git-ignored)                │
│     ├── EXISTS: Load saved configuration                        │
│     └── MISSING: Prompt user for required values               │
│                                                                 │
│  2. Prompt for missing values (interactive)                    │
│     ├── AWS_REGION (default: us-west-2)                        │
│     ├── STACK_NAME (default: pixel-prompt-v2)                  │
│     ├── FLUX_ENABLED (default: true)                           │
│     ├── FLUX_API_KEY (if enabled)                              │
│     ├── FLUX_MODEL_ID (default: flux-pro-1.1)                  │
│     ├── RECRAFT_ENABLED (default: true)                        │
│     ├── RECRAFT_API_KEY (if enabled)                           │
│     ├── GEMINI_ENABLED (default: true)                         │
│     ├── GEMINI_API_KEY (if enabled)                            │
│     ├── OPENAI_ENABLED (default: true)                         │
│     ├── OPENAI_API_KEY (if enabled)                            │
│     └── PROMPT_MODEL_API_KEY (for enhancement)                 │
│                                                                 │
│  3. Save to .deploy-config.json for future runs                │
│                                                                 │
│  4. Generate samconfig.toml programmatically                   │
│     (DO NOT use sam deploy --guided)                           │
│                                                                 │
│  5. Execute: sam build && sam deploy                           │
│                                                                 │
│  6. Parse stack outputs and update frontend/.env               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### .deploy-config.json Schema

```json
{
  "region": "us-west-2",
  "stackName": "pixel-prompt-v2",
  "models": {
    "flux": {
      "enabled": true,
      "apiKey": "bfl_xxxxx",
      "modelId": "flux-pro-1.1"
    },
    "recraft": {
      "enabled": true,
      "apiKey": "recraft_xxxxx",
      "modelId": "recraftv3"
    },
    "gemini": {
      "enabled": true,
      "apiKey": "AIza_xxxxx",
      "modelId": "gemini-2.0-flash-exp"
    },
    "openai": {
      "enabled": true,
      "apiKey": "sk-xxxxx",
      "modelId": "gpt-image-1"
    }
  },
  "promptModel": {
    "provider": "openai",
    "modelId": "gpt-4o",
    "apiKey": "sk-xxxxx"
  },
  "rateLimit": {
    "global": 1000,
    "perIp": 100
  }
}
```

### Generated samconfig.toml

```toml
version = 0.1

[default.deploy.parameters]
stack_name = "pixel-prompt-v2"
region = "us-west-2"
resolve_s3 = true
s3_prefix = "pixel-prompt-v2"
capabilities = "CAPABILITY_IAM"
confirm_changeset = false
fail_on_empty_changeset = false

parameter_overrides = [
  "FluxEnabled=true",
  "FluxApiKey=bfl_xxxxx",
  "FluxModelId=flux-pro-1.1",
  "RecraftEnabled=true",
  "RecraftApiKey=recraft_xxxxx",
  "RecraftModelId=recraftv3",
  "GeminiEnabled=true",
  "GeminiApiKey=AIza_xxxxx",
  "GeminiModelId=gemini-2.0-flash-exp",
  "OpenaiEnabled=true",
  "OpenaiApiKey=sk-xxxxx",
  "OpenaiModelId=gpt-image-1",
  "PromptModelProvider=openai",
  "PromptModelId=gpt-4o",
  "PromptModelApiKey=sk-xxxxx",
  "GlobalRateLimit=1000",
  "IPRateLimit=100"
]
```

### Frontend .env Generation

After successful deployment, parse CloudFormation outputs:

```bash
# Auto-generated by deploy.js
VITE_API_ENDPOINT=https://xxxxx.execute-api.us-west-2.amazonaws.com/Prod
VITE_CLOUDFRONT_DOMAIN=dxxxxxx.cloudfront.net
VITE_S3_BUCKET=pixel-prompt-v2-xxxxx
VITE_ENVIRONMENT=pixel-prompt-v2

# Model configuration (for UI display)
VITE_FLUX_ENABLED=true
VITE_RECRAFT_ENABLED=true
VITE_GEMINI_ENABLED=true
VITE_OPENAI_ENABLED=true
```

---

## Testing Strategy

### Principles

1. **TDD Required**: Write tests before implementation
2. **Mocked Integration**: No live AWS calls in CI
3. **Unit Test Coverage**: 80%+ for new code
4. **Fast Feedback**: Tests complete in <60 seconds

### Backend Testing (Python + pytest)

**Directory Structure:**
```
backend/
├── src/
│   └── ...
└── tests/
    ├── unit/
    │   ├── test_handlers.py      # Provider handler tests
    │   ├── test_context.py       # Context window tests
    │   ├── test_outpaint.py      # Outpaint calculation tests
    │   └── test_manager.py       # Session manager tests
    └── integration/
        └── test_api.py           # Mocked API endpoint tests
```

**Mocking Strategy:**
```python
# Mock S3 client
@pytest.fixture
def mock_s3():
    with mock_s3():
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket='test-bucket')
        yield s3

# Mock provider APIs
@pytest.fixture
def mock_openai(mocker):
    return mocker.patch('models.handlers.OpenAI')

@pytest.fixture
def mock_bfl_api(mocker):
    return mocker.patch('models.handlers.requests.post')
```

**Test Categories:**
1. **Handler Unit Tests**: Mock API responses, verify output format
2. **Context Window Tests**: Verify FIFO behavior, window limits
3. **Outpaint Calculation Tests**: Verify aspect ratio math
4. **Session Manager Tests**: Mock S3, verify lifecycle

### Frontend Testing (Vitest + React Testing Library)

**Directory Structure:**
```
frontend/
├── src/
│   └── ...
└── tests/
    └── __tests__/
        ├── components/
        │   ├── ModelColumn.test.tsx
        │   ├── IterationCard.test.tsx
        │   └── OutpaintControls.test.tsx
        ├── hooks/
        │   ├── useSessionPolling.test.ts
        │   └── useIteration.test.ts
        └── integration/
            └── GenerationFlow.test.tsx
```

**Mocking Strategy:**
```typescript
// Mock API client
vi.mock('@/api/client', () => ({
  generateImages: vi.fn(),
  iterateImage: vi.fn(),
  outpaintImage: vi.fn(),
  getSessionStatus: vi.fn(),
}));

// Mock Zustand store
const mockStore = {
  session: null,
  setSession: vi.fn(),
  // ...
};
vi.mock('@/stores/useAppStore', () => ({
  useAppStore: () => mockStore,
}));
```

**Test Categories:**
1. **Component Unit Tests**: Render, user interaction, props
2. **Hook Tests**: State management, API calls
3. **Integration Tests**: Full user flows with mocked APIs

### CI Pipeline Configuration

**GitHub Actions Workflow (`.github/workflows/test.yml`):**

```yaml
name: Test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: cd frontend && npm ci
      - run: cd frontend && npm run lint
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install ruff
      - run: ruff check backend/src/

  test-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r backend/requirements.txt -r backend/tests/requirements.txt
      - run: PYTHONPATH=backend/src pytest backend/tests/ -v --tb=short

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: cd frontend && npm ci
      - run: cd frontend && npm test
```

**Key Points:**
- No deployment in CI
- All tests use mocks
- Parallel job execution
- Fast failure feedback

---

## Shared Patterns & Conventions

### Commit Message Format

```
type(scope): brief description

Detail 1
Detail 2
```

**Types:** feat, fix, refactor, test, docs, chore
**Scopes:** backend, frontend, deploy, config

**Examples:**
```
feat(backend): add Flux iterate handler

Implement FLUX Fill API integration for image iteration
Add mask generation for full-image refinement
```

```
test(frontend): add ModelColumn component tests

Cover render states: loading, success, error
Test iteration limit warning display
Mock API responses for all scenarios
```

### Error Response Format

**Backend API errors:**
```json
{
  "error": "Human-readable message",
  "code": "ERROR_CODE",
  "details": { "field": "value" }
}
```

**Error Codes:**
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `INVALID_PROMPT`: Content filter triggered
- `MODEL_ERROR`: Provider API failure
- `ITERATION_LIMIT`: Max 7 iterations reached
- `SESSION_NOT_FOUND`: Invalid session ID
- `MODEL_DISABLED`: Requested model not enabled

### API Response Format

**Success responses include:**
```json
{
  "sessionId": "uuid",
  "status": "in_progress|completed|partial|failed",
  "results": [...],
  "metadata": {
    "createdAt": "ISO8601",
    "updatedAt": "ISO8601"
  }
}
```

### TypeScript Conventions

```typescript
// Use strict types, avoid 'any'
interface SessionResult {
  model: 'flux' | 'recraft' | 'gemini' | 'openai';
  status: 'pending' | 'loading' | 'completed' | 'error';
  iterations: IterationResult[];
}

// Use discriminated unions for status
type IterationStatus =
  | { status: 'pending' }
  | { status: 'loading' }
  | { status: 'completed'; imageUrl: string }
  | { status: 'error'; error: string };
```

### Python Conventions

```python
# Use type hints
def iterate_image(
    model_config: Dict[str, str],
    source_image: bytes,
    prompt: str,
    context: List[ContextEntry]
) -> IterationResult:
    """Docstring with Args and Returns."""
    pass

# Use dataclasses for structured data
@dataclass
class ContextEntry:
    iteration: int
    prompt: str
    image_key: str
    timestamp: datetime
```

---

## Phase Verification

### Checklist

- [ ] All ADR documents reviewed and accepted
- [ ] `.deploy-config.json` schema finalized
- [ ] `samconfig.toml` generation logic documented
- [ ] Frontend `.env` generation logic documented
- [ ] Backend test directory structure created
- [ ] Frontend test directory structure created
- [ ] CI workflow file updated (no deploy steps)
- [ ] Commit message format documented
- [ ] Error codes documented
- [ ] TypeScript interfaces outlined
- [ ] Python type hints convention established

### Verification Commands

```bash
# Verify directory structure exists
ls docs/plans/

# Verify CI workflow exists
cat .github/workflows/test.yml

# Verify .gitignore includes deploy config
grep "deploy-config" .gitignore
```

### Known Limitations

1. **No migration path**: Existing jobs won't be converted to sessions
2. **API key rotation**: Requires redeploy (no runtime secret refresh)
3. **Model version changes**: Require config update and redeploy

---

## Next Phase

Proceed to [Phase 1: Backend Transformation](./Phase-1.md) to implement the 4-model system, iteration endpoints, and conversation context management.
