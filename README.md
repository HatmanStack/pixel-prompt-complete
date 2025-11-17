<div align="center">

# Pixel Prompt Complete

[![](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://reactjs.org/)
[![](https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev/)
[![](https://img.shields.io/badge/Python%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![](https://img.shields.io/badge/AWS%20Lambda-FF9900?style=for-the-badge&logo=awslambda&logoColor=white)](https://aws.amazon.com/lambda/)
[![](https://img.shields.io/badge/AWS%20SAM-FF9900?style=for-the-badge&logo=amazonaws&logoColor=white)](https://aws.amazon.com/serverless/sam/)
[![](https://img.shields.io/badge/GitHub%20Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/features/actions)

**Full-stack serverless text-to-image generation platform.**

Complete implementation of Pixel Prompt with React frontend, Python backend, and AWS infrastructure. Deploy to your own AWS account with full control over models, rate limits, and costs.

[View Parent Project](https://github.com/HatmanStack/pixel-prompt) | [Live Demo](https://production.d2iujulgl0aoba.amplifyapp.com/)

---

</div>

## 🎯 What is Pixel Prompt Complete?

Pixel Prompt Complete is the **recommended starting point** for deploying Pixel Prompt to AWS. It's a complete, production-ready implementation that combines:

- **React Frontend** (Vite) - Modern, responsive UI with real-time job polling
- **Python Backend** (AWS Lambda) - Serverless image generation with parallel model execution
- **AWS Infrastructure** - S3 storage, CloudFront CDN, API Gateway
- **CI/CD Pipeline** - GitHub Actions for automated testing and deployment
- **Full Documentation** - Deployment guides, testing guides, and troubleshooting

Unlike other Pixel Prompt variants (container, frontend-only, JS), this submodule provides everything needed for a scalable, production-grade deployment.

---

## ✨ Features

- 🎨 **Multiple AI Models** - Support for 1-20 AI models running in parallel (OpenAI, Google, AWS Bedrock, Stability AI, Black Forest Labs, Recraft)
- ⚡ **Parallel Execution** - All models generate simultaneously, results appear progressively
- 🖼️ **Gallery Browser** - Browse and revisit historical generations
- 🤖 **Prompt Enhancement** - AI-powered prompt improvement using LLMs
- 📊 **Real-time Status** - Live updates as each model completes
- 🌐 **CloudFront CDN** - Fast global image delivery
- 🔒 **Rate Limiting** - Configurable global and per-IP rate limits with whitelist support
- 🛡️ **Content Filtering** - NSFW detection and keyword filtering
- 📈 **CloudWatch Monitoring** - Automatic alarms for errors and performance
- 💰 **Cost Optimized** - Serverless architecture, pay only for what you use (~$5-20/month)

---

## 🚀 Supported AI Models

Configure any combination of these providers (up to 20 models):

### Diffusion Models
- **OpenAI** - DALL-E 3
- **Google** - Gemini 2.0, Imagen 3.0
- **AWS Bedrock** - Nova Canvas, Stable Diffusion 3.5 Large
- **Black Forest Labs** - Flux Pro, Flux Dev
- **Stability AI** - Stable Diffusion Turbo, Ultra
- **Recraft** - Recraft v3

### Prompt Enhancement
- **Meta Llama** - llama-4-maverick-17b-128e-instruct (via configured provider)

---

## 💻 Tech Stack

### Frontend
- **Framework:** React 19 with Vite
- **Styling:** CSS Modules
- **HTTP Client:** Fetch API with correlation IDs
- **State:** React Context API
- **Testing:** Vitest + React Testing Library (145 tests)

### Backend
- **Runtime:** Python 3.12 on AWS Lambda
- **Framework:** AWS SAM (Serverless Application Model)
- **Storage:** S3 + CloudFront CDN
- **API:** API Gateway HTTP API with CORS
- **AI SDKs:** openai, google-genai, boto3 (Bedrock)
- **Testing:** pytest (88 unit tests + integration tests)

### Infrastructure
- **Compute:** AWS Lambda (3008 MB, 15-minute timeout)
- **Storage:** S3 with 30-day lifecycle
- **CDN:** CloudFront with Origin Access Identity
- **Monitoring:** CloudWatch Logs + Alarms
- **CI/CD:** GitHub Actions (test, staging, production workflows)

---

## 🚀 Quick Start

### Prerequisites

- [AWS Account](https://aws.amazon.com/) with permissions for Lambda, S3, CloudFront, API Gateway, IAM
- [AWS CLI](https://aws.amazon.com/cli/) configured: `aws configure`
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) installed: `sam --version`
- [Node.js](https://nodejs.org/) v18+
- [Python](https://www.python.org/) 3.12+
- API keys for desired AI models (OpenAI, Google, etc.)

### First-Time Deployment

**Initial setup with SAM** - configure models and API keys:

```bash
# Clone repository
git clone --recurse-submodules https://github.com/HatmanStack/pixel-prompt.git
cd pixel-prompt/pixel-prompt-complete/backend

# Build Lambda function
sam build

# Interactive deployment (prompts for all configuration)
sam deploy --guided
```

**During `--guided` setup, you'll configure:**
- Stack name (e.g., `pixel-prompt-prod`)
- AWS Region (e.g., `us-east-1`)
- **ModelCount**: How many AI models (1-20)
- **Model1Name through Model20Name**: AI model names (e.g., "DALL-E 3", "Gemini 2.0")
- **Model1Key through Model20Key**: API keys for each model
- **PromptModelIndex**: Which model to use for prompt enhancement
- **Rate limits**: GlobalRateLimit, IPRateLimit, IPWhitelist

**✅ Configuration is saved to `samconfig.toml`** (gitignored - safe to store API keys)

**Then configure frontend:**
```bash
# Get API endpoint
sam list stack-outputs --stack-name pixel-prompt-prod

# Configure frontend
cd ../frontend
cp .env.example .env
# Edit .env and paste the ApiEndpoint URL

# Build and test
npm install
npm run build
npm run preview
```

---

### Subsequent Deployments

**After initial setup**, use the automated script for faster deployments:

```bash
# Deploy backend (uses saved samconfig.toml)
./scripts/deploy.sh dev|staging|prod
```

**The script automatically:**
- ✅ Builds and deploys backend using saved configuration
- ✅ Extracts API endpoint from CloudFormation
- ✅ **Auto-generates `frontend/.env` file** with correct endpoint
- ✅ Validates API accessibility
- ✅ Displays next steps

**Or deploy manually:**
```bash
cd backend
sam build
sam deploy              # Uses saved config
# or
sam deploy --config-env prod   # Use specific environment
```

---

## 📋 Available Scripts

### Backend Commands

```bash
cd backend

# Build Lambda function
sam build

# Deploy to AWS
sam deploy                              # Use saved config
sam deploy --config-env dev|staging|prod  # Environment-specific
sam deploy --guided                     # Interactive setup

# Local testing
sam local invoke -e events/generate.json
sam local start-api

# View logs
sam logs --stack-name <name> --tail

# Run tests
pip install -r requirements.txt -r tests/requirements.txt
pytest tests/unit/ -v                   # Unit tests (88 tests)
pytest tests/unit/ --cov=src            # With coverage
pytest tests/integration/ -v            # Integration tests (requires deployed backend)

# Delete stack
sam delete --stack-name <name>
```

### Frontend Commands

```bash
cd frontend

# Development
npm install
npm run dev                # Start dev server (port 3000)
npm run preview            # Preview production build

# Production
npm run build              # Build to dist/

# Testing
npm test                   # Run all tests (145 tests)
npm test -- --watch        # Watch mode
npm run test:ui            # Interactive test UI
npm run test:coverage      # Coverage report

# Linting
npm run lint
```

### Utility Scripts

```bash
# Benchmark Lambda performance
./scripts/benchmark-lambda.sh <api-endpoint>

# Load testing with Artillery
./scripts/run-loadtest.sh <api-endpoint>

# Test CloudFront image delivery
./scripts/test-cloudfront.sh <api-endpoint>

# Frontend performance audit
./scripts/lighthouse-audit.sh <frontend-url>
```

---

## 📁 Project Structure

```
pixel-prompt-complete/
├── backend/
│   ├── src/
│   │   ├── lambda_function.py      # Main handler
│   │   ├── models/                 # Model registry & handlers
│   │   ├── jobs/                   # Job lifecycle management
│   │   ├── api/                    # Enhance & logging endpoints
│   │   └── utils/                  # Storage, rate limiting, filtering
│   ├── tests/
│   │   ├── unit/                   # 88 unit tests
│   │   └── integration/            # End-to-end API tests
│   ├── template.yaml               # CloudFormation/SAM template
│   └── samconfig.toml              # SAM deployment config
├── frontend/
│   ├── src/
│   │   ├── api/                    # API client with correlation IDs
│   │   ├── components/             # React components
│   │   ├── hooks/                  # Custom hooks (polling, gallery)
│   │   └── utils/                  # Helpers, logging, image utils
│   ├── __tests__/                  # 145 tests (122 unit + 23 integration)
│   └── vite.config.js
├── scripts/
│   ├── deploy.sh                   # Automated deployment
│   ├── benchmark-lambda.sh         # Performance testing
│   ├── run-loadtest.sh             # Load testing
│   └── test-cloudfront.sh          # CDN testing
├── .github/workflows/
│   ├── test.yml                    # CI tests + linting
│   ├── deploy-staging.yml          # Auto-deploy to staging
│   └── deploy-production.yml       # Manual production deploy
└── CLAUDE.md                       # Development guide for Claude Code
```

---

## 🔧 Configuration

### Model Configuration

Configure 1-20 AI models via SAM parameters:

```yaml
Parameters:
  ModelCount: 9
  Model1Name: "DALL-E 3"
  Model1Key: "sk-..."
  Model2Name: "Gemini 2.0"
  Model2Key: "AIza..."
  # ... up to Model20Name/Model20Key
```

**AWS Bedrock Models**: Set API key to `"N/A"` and ensure Lambda role has `bedrock-runtime:InvokeModel` permissions.

### Rate Limiting

```yaml
Parameters:
  GlobalRateLimit: 1000      # Requests per hour (all IPs)
  IPRateLimit: 50            # Requests per day per IP
  IPWhitelist: "1.2.3.4,5.6.7.8"  # Bypass rate limits
```

### Environment-Specific Configs

Edit `backend/samconfig.toml` to customize dev/staging/prod:
- Model counts (3 for dev, 9 for staging/prod)
- Rate limits (lower for dev, higher for prod)
- Stack names and regions

---

## 📊 CI/CD Pipeline

### Automated Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| **Tests** | PR, push to main | Frontend & backend tests + linting |
| **Deploy Staging** | Push to main | Auto-deploy to AWS staging environment |
| **Deploy Production** | Manual | Deploy to production with confirmation |

### For Contributors

1. Create PR → Automated tests run
2. All tests must pass before merge
3. After merge → Auto-deploy to staging
4. Maintainers manually deploy to production

See [parent project workflows](https://github.com/HatmanStack/pixel-prompt#cicd-pipeline) for detailed CI/CD documentation.

---

## 💰 Cost Estimation

Expected monthly costs for moderate usage (~1000 generations/month):

- **Lambda**: ~$0.20 (compute time)
- **S3**: ~$0.50 (storage)
- **CloudFront**: ~$1.00 (data transfer)
- **API Gateway**: ~$1.00 (requests)
- **AI Model APIs**: Variable (depends on chosen models and usage)

**Total AWS Infrastructure**: $5-10/month + AI API costs

---

## 📖 Documentation

- **[Backend README](./backend/README.md)** - Detailed backend documentation
- **[Frontend README](./frontend/README.md)** - Frontend development guide
- **[Backend Testing Guide](./backend/TESTING.md)** - 88 unit tests + integration testing
- **[Frontend Testing Guide](./frontend/TESTING.md)** - 145 tests with Vitest
- **[Backend Deployment](./backend/DEPLOYMENT.md)** - AWS deployment details
- **[Frontend Deployment](./frontend/DEPLOYMENT.md)** - Static hosting options
- **[CLAUDE.md](./CLAUDE.md)** - Development guide for Claude Code

---

## 🐛 Troubleshooting

**Images not displaying?**
- CloudFront distribution takes 10-15 minutes to deploy
- Check S3 bucket policy allows CloudFront OAI access

**Rate limit errors?**
- Check `rate-limits/` objects in S3 bucket
- Adjust `GlobalRateLimit` or `IPRateLimit` parameters
- Add IPs to `IPWhitelist`

**Model failures?**
- Check CloudWatch logs for API key validity
- Verify quota limits with AI provider
- AWS Bedrock models are region-specific (Nova: us-east-1, SD: us-west-2)

**Frontend can't connect?**
- Verify `VITE_API_ENDPOINT` in frontend `.env`
- Check CORS settings in API Gateway (should allow `*`)
- Confirm backend deployed successfully

See detailed troubleshooting in [backend README](./backend/README.md#troubleshooting).

---

## 🤝 Contributing

This is a submodule of the [main Pixel Prompt project](https://github.com/HatmanStack/pixel-prompt).

For contributions:
1. Create issues in the parent repository
2. Follow coding conventions in [CLAUDE.md](./CLAUDE.md)
3. Run tests before submitting PRs: `npm test` (frontend) and `pytest tests/unit/` (backend)
4. All PRs require passing CI checks

---

## 📜 License

This project is licensed under the Apache 2.0 License. See [parent repository](https://github.com/HatmanStack/pixel-prompt) for full license details.

---

## 🔗 Related Projects

Part of the Pixel Prompt ecosystem:

- **[pixel-prompt](https://github.com/HatmanStack/pixel-prompt)** - Main repository with all implementation variants
- **[pixel-prompt-backend](https://github.com/HatmanStack/pixel-prompt-backend)** - FastAPI/Docker backend
- **[pixel-prompt-frontend](https://github.com/HatmanStack/pixel-prompt-frontend)** - React Native/Expo mobile app
- **[pixel-prompt-container](https://github.com/HatmanStack/pixel-prompt-container)** - Dockerized full-stack deployment
- **[pixel-prompt-js](https://github.com/HatmanStack/pixel-prompt-js)** - JavaScript-only implementation

---

<div align="center">

**Built with AWS SAM, React, and Python**

[Documentation](./CLAUDE.md) · [Report Bug](https://github.com/HatmanStack/pixel-prompt/issues) · [Request Feature](https://github.com/HatmanStack/pixel-prompt/issues)

</div>
