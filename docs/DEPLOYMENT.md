# Deployment Guide

## Prerequisites

1. **AWS CLI** configured: `aws configure`
2. **AWS SAM CLI** installed: `pip install aws-sam-cli`
3. **Python 3.12+** for backend
4. **Node.js 18+** for frontend
5. API keys for your chosen AI models

## Backend Deployment

### First-Time Setup

```bash
cd backend
sam build
sam deploy --guided
```

You'll be prompted for:

| Parameter | Description | Example |
|-----------|-------------|---------|
| Stack Name | CloudFormation stack name | `pixel-prompt-prod` |
| AWS Region | Deployment region | `us-east-1` |
| ModelCount | Number of AI models (1-20) | `5` |
| Model{N}Provider | Provider type | `openai`, `google_gemini`, `bedrock_nova` |
| Model{N}Id | Model identifier | `dall-e-3`, `flux-pro-1.1` |
| Model{N}ApiKey | API key (leave blank for Bedrock) | `sk-...` |
| PromptModelIndex | Model for prompt enhancement (1-based) | `1` |
| GlobalRateLimit | Requests per hour (all IPs) | `1000` |
| IPRateLimit | Requests per day per IP | `50` |
| IPWhitelist | IPs to bypass rate limits | `1.2.3.4,5.6.7.8` |

Configuration is saved to `samconfig.toml` for subsequent deploys.

### Subsequent Deploys

```bash
cd backend
sam build && sam deploy
```

### Get Stack Outputs

```bash
sam list stack-outputs --stack-name <stack-name>
```

Save `ApiEndpoint` for frontend configuration.

## Frontend Deployment

```bash
cd frontend
npm install
echo "VITE_API_ENDPOINT=https://xxx.execute-api.region.amazonaws.com/Prod" > .env
npm run build
```

Deploy `dist/` to any static host (S3, Amplify, Vercel, Netlify).

## Provider Configuration

### OpenAI (DALL-E)
- Provider: `openai`
- Model ID: `dall-e-3`
- API Key: Required - [Get key](https://platform.openai.com/api-keys)

### Google Gemini
- Provider: `google_gemini`
- Model ID: `gemini-2.0-flash-exp`
- API Key: Required - [Get key](https://ai.google.dev/)

### AWS Bedrock (Nova Canvas)
- Provider: `bedrock_nova`
- Model ID: `amazon.nova-canvas-v1:0`
- API Key: Leave blank (uses Lambda IAM role)
- Requires `bedrock-runtime:InvokeModel` permission

### Black Forest Labs (Flux)
- Provider: `bfl`
- Model ID: `flux-pro-1.1` or `flux-dev`
- API Key: Required - [Get key](https://api.bfl.ai/)

### Recraft
- Provider: `recraft`
- Model ID: `recraft-v3`
- API Key: Required - [Get key](https://www.recraft.ai/)

### Generic (OpenAI-Compatible)
- Provider: `generic`
- Model ID: Your API's model name
- API Key: As required
- Base URL: **Required** - Your API endpoint

## Monitoring

```bash
# View logs
sam logs --stack-name <stack-name> --tail

# Check stack status
aws cloudformation describe-stacks --stack-name <stack-name>
```

## Troubleshooting

**Images not displaying**
- CloudFront takes 10-15 minutes to deploy initially
- Verify S3 bucket policy allows CloudFront OAI access

**Rate limit exceeded**
- Check `rate-limits/` objects in S3
- Adjust `GlobalRateLimit`/`IPRateLimit` parameters
- Add IPs to `IPWhitelist`

**Model failures**
- Check CloudWatch logs for API key issues
- Verify provider quota limits
- Bedrock models are region-specific (Nova: us-east-1)

**Frontend can't connect**
- Verify `VITE_API_ENDPOINT` in `.env`
- Check CORS in API Gateway (should allow `*`)

**Prompt enhancement not working**
- Verify `PromptModelIndex` is valid (1 to ModelCount)
- Check CloudWatch for `[ENHANCE]` errors

## Cleanup

```bash
# Delete stack (S3 bucket retained)
sam delete --stack-name <stack-name>

# Delete S3 bucket manually if desired
aws s3 rm s3://<bucket-name> --recursive
aws s3 rb s3://<bucket-name>
```
