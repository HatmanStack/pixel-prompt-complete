<div align="center">
<h1>Pixel Prompt Complete</h1>

<h4>
<a href="https://www.apache.org/licenses/LICENSE-2.0.html"><img src="https://img.shields.io/badge/license-Apache2.0-blue" alt="Apache 2.0 license" /></a>
<a href="https://reactjs.org/"><img src="https://img.shields.io/badge/React-19-61DAFB" alt="React 19" /></a>
<a href="https://aws.amazon.com/lambda/"><img src="https://img.shields.io/badge/AWS-Lambda-FF9900" alt="AWS Lambda" /></a>
<a href="https://docs.aws.amazon.com/serverless-application-model/"><img src="https://img.shields.io/badge/AWS-SAM-FF9900" alt="AWS SAM" /></a>
</h4>

<p><b>Serverless text-to-image generation with parallel AI model execution</b><br>
<a href="https://production.d2iujulgl0aoba.amplifyapp.com/">Pixel Prompt »</a></p>

<p>Submit a prompt, generate images from multiple AI models simultaneously,
browse results in a gallery. Deploy to your own AWS account with full control
over models, rate limits, and costs.</p>
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
- **AWS CLI** configured with credentials (`aws configure`)
- **AWS SAM CLI** for serverless deployment
- **Python 3.12+** for backend Lambda functions

## Quick Start

```bash
cd backend
sam build
sam deploy --guided   # Configure models, API keys, rate limits

cd ../frontend
npm install
npm run dev
```

## Deployment

```bash
cd backend && sam build && sam deploy
```

The guided setup prompts for:

| Prompt | Description |
|--------|-------------|
| Stack Name | CloudFormation stack name (e.g., `pixel-prompt-prod`) |
| AWS Region | Deployment region (e.g., `us-east-1`) |
| ModelCount | Number of AI models to use (1-20) |
| Model{N}Provider | Provider type (`openai`, `google_gemini`, `bedrock_nova`, etc.) |
| Model{N}ApiKey | API key (leave blank for Bedrock) |
| Rate Limits | Global/per-IP limits and whitelist |

Configuration saved to `samconfig.toml`. Subsequent deploys use saved config.

See [docs/README.md](docs/README.md) for full documentation.
