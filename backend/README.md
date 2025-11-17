# Pixel Prompt Complete - Backend

Serverless backend for Pixel Prompt Complete, a text-to-image generation platform supporting multiple AI models in parallel.

## Overview

This backend is built using AWS Lambda, S3, CloudFront, and API Gateway, managed through AWS SAM (Serverless Application Model). It provides a fully serverless, scalable infrastructure for generating images from multiple AI providers simultaneously.

## Architecture

```
User → API Gateway → Lambda Function → External AI APIs (OpenAI, Google, Stability AI, etc.)
                           ↓
                        S3 Bucket → CloudFront Distribution
```

### Key Components

- **Lambda Function**: Python 3.12 runtime executing image generation requests
- **Dynamic Model Registry**: Configure 1-20 AI models via environment variables
- **Intelligent Routing**: Automatic provider detection from model names
- **Parallel Execution**: Generate images from all models concurrently
- **Async Job Management**: Job tracking with real-time status updates
- **S3 Storage**: Stores generated images and job status
- **CloudFront CDN**: Fast image delivery worldwide
- **API Gateway**: HTTP API with CORS support

## Prerequisites

- **AWS CLI**: v2+ configured with credentials (`aws configure`)
- **AWS SAM CLI**: Latest version (`sam --version` shows 1.100+)
- **Python**: 3.12+
- **Node.js**: v18+ (for frontend development)
- **API Keys**: For desired AI models (OpenAI, Stability AI, Google, etc.)

### AWS Account Requirements

- Active AWS account with permissions for:
  - Lambda, S3, CloudFront, API Gateway, IAM
- AWS Bedrock access enabled (for Nova Canvas and Stable Diffusion models)
- Sufficient service quotas

## Supported AI Models

The backend supports these AI providers with intelligent routing:

- **OpenAI**: DALL-E 3
- **Google**: Gemini 2.0, Imagen 3.0
- **AWS Bedrock**: Nova Canvas, Stable Diffusion 3.5 Large
- **Stability AI**: Stable Diffusion variants
- **Black Forest Labs**: Flux models (Pro, Dev)
- **Recraft**: Recraft v3
- **Generic**: Any OpenAI-compatible API

## Quick Start

### 1. Build

```bash
cd backend
sam build
```

### 2. Deploy

First deployment (interactive):
```bash
sam deploy --guided
```

Follow prompts to configure:
- Stack name (e.g., `pixel-prompt-complete-dev`)
- AWS Region (e.g., `us-west-2`)
- Model configurations (names and API keys)
- Rate limits

Subsequent deployments:
```bash
sam deploy
```

### 3. Get Outputs

```bash
sam list stack-outputs --stack-name <stack-name>
```

Save the API endpoint URL for frontend configuration.

### 4. Test

```bash
API_ENDPOINT="<from outputs>"

# Test image generation
curl -X POST $API_ENDPOINT/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"beautiful sunset","steps":25,"guidance":7,"ip":"1.2.3.4"}'

# Get job status
curl $API_ENDPOINT/status/<job-id>

# Enhance prompt
curl -X POST $API_ENDPOINT/enhance \
  -H "Content-Type: application/json" \
  -d '{"prompt":"cat"}'
```

## Configuration

### Model Configuration

Configure models via SAM parameters:

- **ModelCount**: Number of models to use (1-20)
- **Model1Name** through **Model20Name**: Model names
- **Model1Key** through **Model20Key**: API keys
- **PromptModelIndex**: Which model to use for prompt enhancement (1-based)

Example:
```yaml
Parameters:
  ModelCount: 9
  Model1Name: "DALL-E 3"
  Model1Key: "sk-..."
  Model2Name: "Gemini 2.0"
  Model2Key: "AIza..."
  # ... etc
```

### Rate Limiting

- **GlobalRateLimit**: Maximum requests per hour (all IPs)
- **IPRateLimit**: Maximum requests per day per IP
- **IPWhitelist**: Comma-separated IPs to bypass limits

### AWS Credentials

For AWS Bedrock models, configure:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

## API Endpoints

### POST /generate

Create image generation job.

**Request:**
```json
{
  "prompt": "beautiful mountain sunset",
  "steps": 25,
  "guidance": 7,
  "control": 1.0,
  "ip": "1.2.3.4"
}
```

**Response:**
```json
{
  "jobId": "uuid-v4-string"
}
```

### GET /status/{jobId}

Get job status and results.

**Response:**
```json
{
  "jobId": "uuid",
  "status": "in_progress",
  "totalModels": 9,
  "completedModels": 3,
  "results": [
    {
      "model": "DALL-E 3",
      "status": "completed",
      "imageKey": "s3-key",
      "completedAt": "2025-11-15T14:30:45Z"
    }
  ]
}
```

### POST /enhance

Enhance prompt using configured LLM.

**Request:**
```json
{
  "prompt": "cat"
}
```

**Response:**
```json
{
  "enhanced": "A photorealistic cat sitting on a windowsill..."
}
```

## Testing

### Unit Tests

Run unit tests (88 tests covering core modules):
```bash
cd backend
pip install -r requirements.txt -r tests/requirements.txt
python -m pytest tests/unit/ -v
```

Test coverage:
```bash
pytest tests/unit/ --cov=src --cov-report=html
open htmlcov/index.html  # View coverage report
```

### Integration Tests

Run integration tests against deployed backend:
```bash
export API_ENDPOINT="https://your-api.execute-api.region.amazonaws.com/Prod"
pytest tests/integration/ -v
```

See [TESTING.md](./TESTING.md) for comprehensive testing guide.

## Development

### Project Structure

```
backend/
├── src/
│   ├── lambda_function.py    # Main handler
│   ├── config.py             # Environment variable loading
│   ├── models/
│   │   ├── registry.py       # Model registry
│   │   └── handlers.py       # Provider handlers
│   ├── jobs/
│   │   ├── manager.py        # Job lifecycle
│   │   └── executor.py       # Parallel execution
│   ├── api/
│   │   └── enhance.py        # Prompt enhancement
│   └── utils/
│       ├── storage.py        # S3 operations
│       ├── rate_limit.py     # Rate limiting
│       └── content_filter.py # NSFW detection
├── template.yaml             # SAM template
├── requirements.txt          # Python dependencies
└── tests/
```

### Local Testing

Test Lambda locally:
```bash
sam local invoke -e events/generate.json
```

Start local API:
```bash
sam local start-api
```

### Deployment Variations

Update model configuration:
```bash
sam deploy --parameter-overrides ModelCount=10 Model1Key=new-key
```

Deploy to different environment:
```bash
sam deploy --stack-name pixel-prompt-complete-prod --parameter-overrides Environment=prod
```

## Monitoring

### CloudWatch Logs

View logs:
```bash
sam logs --stack-name <stack-name> --tail
```

### CloudWatch Alarms

The stack creates alarms for:
- Lambda errors (> 5 errors in 5 minutes)
- Lambda duration (average > 2 minutes)

## Cost Estimation

Expected monthly cost for moderate usage (~1000 generations/month):

- Lambda: ~$0.20 per 1M requests + compute time
- S3: ~$0.023 per GB storage
- CloudFront: ~$0.085 per GB transfer
- API Gateway: ~$1.00 per 1M requests

**Total: $5-20/month** depending on usage

## Cleanup

Delete stack and resources:
```bash
sam delete --stack-name <stack-name>
```

**Note**: S3 bucket is retained by default to prevent data loss. Delete manually if needed:
```bash
aws s3 rb s3://<bucket-name> --force
```

## Troubleshooting

### Deployment Fails

- Check CloudFormation events: `aws cloudformation describe-stack-events --stack-name <name>`
- Verify IAM permissions
- Check CloudWatch logs for Lambda errors

### API Returns Errors

- Check Lambda logs: `sam logs --stack-name <name> --tail`
- Verify API keys are correct
- Check rate limits (may need to increase)

### Images Not Displaying

- Verify CloudFront distribution deployed (takes 10-15 minutes)
- Check S3 bucket policy allows CloudFront access
- Verify CORS configuration

### Model-Specific Issues

- **AWS Bedrock**: Verify access enabled in correct region (Nova: us-east-1, SD: us-west-2)
- **Google**: Check API key has Gemini/Imagen enabled
- **OpenAI**: Verify API key and quota limits

## Documentation

- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [Implementation Plan](../docs/plans/Phase-1.md)
- [Architecture Decisions](../docs/plans/Phase-0.md)

## License

Apache 2.0
