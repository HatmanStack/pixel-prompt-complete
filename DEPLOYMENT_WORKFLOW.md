# Deployment Workflow

Quick reference for deploying backend and updating frontend.

## After SAM Deployment

Whenever you deploy the backend with SAM, update the frontend .env file:

```bash
# Deploy backend
cd backend
sam build
sam deploy --config-env prod

# Auto-update frontend .env
cd ..
npm run update-env

# Start frontend
cd frontend
npm run dev
```

## Available Commands

| Command | Description |
|---------|-------------|
| `npm run update-env` | Update .env for prod stack (default) |
| `npm run update-env:dev` | Update .env for dev stack |
| `npm run update-env:staging` | Update .env for staging stack |
| `npm run update-env:prod` | Update .env for prod stack |

## What It Does

The `update-env` script:
1. Queries CloudFormation for the ApiEndpoint output
2. Writes it to `frontend/.env` as `VITE_API_ENDPOINT`
3. Shows you the updated contents

## Manual Method (If Needed)

```bash
# Get API endpoint
sam list stack-outputs --stack-name pixel-prompt-prod

# Manually edit frontend/.env
cd frontend
echo "VITE_API_ENDPOINT=https://your-api-endpoint" > .env
```

## One-Liner Workflow

```bash
cd backend && sam build && sam deploy --config-env prod && cd .. && npm run update-env && cd frontend && npm run dev
```
