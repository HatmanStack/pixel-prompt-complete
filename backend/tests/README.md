# Pixel Prompt Complete - Backend Tests

## Overview

Integration tests for the Pixel Prompt Complete backend API endpoints.

## Prerequisites

1. **Python 3.12+**
2. **Deployed backend** OR **SAM Local**:
   - Deployed: Set `API_ENDPOINT` environment variable
   - Local: Run `sam local start-api` in backend directory

## Installation

```bash
cd backend/tests
pip install -r requirements.txt
```

## Running Tests

### All Tests (Excluding Slow)

```bash
pytest tests/integration/ -v -m "not slow"
```

### All Tests (Including Slow AI Generation Tests)

```bash
export API_ENDPOINT="https://your-api.execute-api.us-west-2.amazonaws.com/Prod"
pytest tests/integration/ -v
```

### Specific Test Class

```bash
pytest tests/integration/test_api_endpoints.py::TestPromptEnhancement -v
```

### With Coverage

```bash
pytest tests/integration/ --cov=../src --cov-report=html
```

## Test Categories

### Fast Tests (Default)
- Health checks
- Input validation
- Prompt enhancement
- Gallery endpoints
- Error handling

### Slow Tests (`@pytest.mark.slow`)
- Full image generation workflow
- Job status polling
- Multi-model execution

## Environment Variables

- `API_ENDPOINT`: API Gateway endpoint URL (required)
  - Example: `https://abc123.execute-api.us-west-2.amazonaws.com/Prod`
  - Local: `http://localhost:3000`

## Expected Results

**All Fast Tests**: ~10-30 seconds
**All Tests (with slow)**: ~5-10 minutes (depends on AI API response times)

## CI/CD Integration

Add to GitHub Actions:

```yaml
- name: Run Backend Integration Tests
  env:
    API_ENDPOINT: ${{ secrets.API_ENDPOINT }}
  run: |
    cd backend/tests
    pip install -r requirements.txt
    pytest integration/ -v -m "not slow"
```

## Troubleshooting

**API_ENDPOINT not set**:
```bash
export API_ENDPOINT="https://your-api-url.com/Prod"
```

**Tests fail with "Connection refused"**:
- Verify API endpoint is accessible
- Check SAM local is running (if testing locally)
- Verify VPN/network access

**Authentication errors**:
- This is a public API, no auth required
- If rate limited, wait and retry

## Notes

- Tests use real API endpoints (no mocking for integration tests)
- Slow tests may incur API costs (AI model calls)
- Tests are idempotent and can be run multiple times
- No test data cleanup needed (S3 lifecycle handles old data)
