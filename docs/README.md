<div align="center">
<h1>Pixel Prompt Complete</h1>

<h4>
<a href="https://www.apache.org/licenses/LICENSE-2.0.html"><img src="https://img.shields.io/badge/license-Apache2.0-blue" alt="Apache 2.0 license" /></a>
<a href="https://reactjs.org/"><img src="https://img.shields.io/badge/React-19-61DAFB" alt="React 19" /></a>
<a href="https://aws.amazon.com/lambda/"><img src="https://img.shields.io/badge/AWS-Lambda-FF9900" alt="AWS Lambda" /></a>
<a href="https://docs.aws.amazon.com/serverless-application-model/"><img src="https://img.shields.io/badge/AWS-SAM-FF9900" alt="AWS SAM" /></a>
</h4>

<p><b>Serverless text-to-image generation with parallel AI model execution</b><br>
<a href="https://production.d2iujulgl0aoba.amplifyapp.com/">Live Demo »</a></p>

<p>Submit a prompt, generate images from multiple AI models simultaneously, browse results in a gallery. Deploy to your own AWS account with full control over models, rate limits, and costs.</p>
</div>

## Structure

```text
├── frontend/   # React + Vite client
├── backend/    # AWS Lambda (Python 3.12)
├── scripts/    # Deployment & testing utilities
└── docs/       # Documentation
```

## Prerequisites

- **Node.js** v18+ (v24 LTS recommended)
- **Python** 3.12+
- **AWS CLI** configured (`aws configure`)
- **AWS SAM CLI** for serverless deployment
- API keys for desired AI models

## Quick Start

```bash
# Backend deployment
cd backend
sam build
sam deploy --guided    # Interactive setup for models, API keys, rate limits

# Frontend setup
cd ../frontend
npm install
echo "VITE_API_ENDPOINT=<your-api-endpoint>" > .env
npm run dev
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed configuration.

## Features

- **Multiple AI Models** - 1-20 models running in parallel (OpenAI, Google, Bedrock, Stability, BFL, Recraft)
- **Parallel Execution** - All models generate simultaneously, results appear progressively
- **Gallery Browser** - Browse and revisit historical generations
- **Prompt Enhancement** - AI-powered prompt improvement
- **Rate Limiting** - Configurable global and per-IP limits with whitelist
- **Content Filtering** - NSFW detection and keyword filtering
- **CloudFront CDN** - Fast global image delivery

## Supported Models

| Provider | Models | API Key Required |
|----------|--------|------------------|
| OpenAI | DALL-E 3 | Yes |
| Google | Gemini 2.0, Imagen 3.0 | Yes |
| AWS Bedrock | Nova Canvas, SD 3.5 | No (uses IAM) |
| Black Forest Labs | Flux Pro, Flux Dev | Yes |
| Stability AI | SD Turbo, Ultra | Yes |
| Recraft | Recraft v3 | Yes |

## Architecture

**Frontend**: React 19 + Vite
- Context-based state management
- Real-time job polling (2s intervals)
- Progressive image loading

**Backend**: AWS Lambda (Python 3.12)
- ThreadPoolExecutor for parallel model execution
- S3 for job state and image storage
- CloudFront for CDN delivery

**Flow**: User submits prompt → API Gateway → Lambda spawns threads per model → Results stored in S3 → CloudFront delivers images

## Testing

```bash
# Frontend (145 tests)
cd frontend
npm test
npm run test:coverage

# Backend (88 tests)
cd backend
pip install -r requirements.txt -r tests/requirements.txt
pytest tests/unit/ -v
pytest tests/unit/ --cov=src
```

## Cost Estimate

~1000 generations/month:
- **AWS Infrastructure**: $5-10/month
- **AI APIs**: Variable by provider

## License

Apache 2.0 - See [parent repository](https://github.com/HatmanStack/pixel-prompt) for details.
