# Backend - Quick Deployment

Python 3.12 serverless backend for AWS Lambda. See [root README](../README.md) for full documentation.

## Prerequisites

- [AWS CLI](https://aws.amazon.com/cli/) configured: `aws configure`
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html): `sam --version`
- Python 3.12+
- API keys for AI models (OpenAI, Google, etc.)

## Deploy

```bash
# Build Lambda function
sam build

# First deployment (interactive - configures all models and API keys)
sam deploy --guided
```

During `--guided` setup, configure:
- Stack name (e.g., `pixel-prompt-prod`)
- AWS Region
- ModelCount (1-20)
- For each model:
  - Provider (openai, google_gemini, bedrock_nova, etc.)
  - Model ID (dall-e-3, flux-pro-1.1, etc.)
  - API Key (optional - leave blank for Bedrock)
  - Base URL (optional - for custom APIs)
  - User ID (optional - if provider needs it)
- PromptModelIndex (which model for prompt enhancement)
- Rate limits (GlobalRateLimit, IPRateLimit, IPWhitelist)

**Configuration saved to `samconfig.toml`** (gitignored - safe to store API keys)

**Subsequent deployments:**
```bash
sam build
sam deploy              # Uses saved config
# or
sam deploy --config-env prod   # Specific environment
```

## Configure Frontend

**After deployment**, use the deploy script to auto-generate frontend `.env`:

```bash
cd ..
./scripts/deploy.sh prod
```

This automatically extracts API endpoint and creates `frontend/.env`.

**Or manually:**
```bash
sam list stack-outputs --stack-name pixel-prompt-prod
# Copy ApiEndpoint to frontend/.env
```

## Test

```bash
# View logs
sam logs --stack-name pixel-prompt-dev --tail

# Test locally
sam local invoke -e events/generate.json
sam local start-api
```

## Run Tests

```bash
# Install dependencies
pip install -r src/requirements.txt -r tests/requirements.txt

# Unit tests (88 tests)
pytest tests/unit/ -v

# Integration tests (requires deployed backend)
export API_ENDPOINT="https://..."
pytest tests/integration/ -v
```

## Delete

```bash
sam delete --stack-name pixel-prompt-dev
```

---

**Detailed Documentation:**
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Complete deployment guide
- [TESTING.md](./TESTING.md) - Testing guide
- [Root README](../README.md) - Full project documentation
