# Frontend - Quick Deployment

React + Vite frontend for Pixel Prompt. See [root README](../README.md) for full documentation.

## Prerequisites

- Node.js 18+
- Backend deployed with API endpoint URL

## Setup

```bash
# Install dependencies
npm install
```

**Configure environment:**

**Option 1: Auto-configure (Recommended)**
```bash
# Deploy script auto-generates .env with API endpoint
cd ..
./scripts/deploy.sh prod
```

**Option 2: Manual**
```bash
cp .env.example .env
# Edit .env and set VITE_API_ENDPOINT to your API Gateway URL
```

## Development

```bash
npm run dev          # Start dev server (port 3000)
npm run lint         # Run ESLint
```

## Testing

```bash
npm test                    # Run all tests (145 tests)
npm test -- --watch         # Watch mode
npm run test:coverage       # Coverage report
```

## Production Build

```bash
npm run build        # Build to dist/
npm run preview      # Preview production build
```

## Deploy

Deploy `dist/` folder to any static hosting:

**AWS S3 + CloudFront:**
```bash
aws s3 sync dist/ s3://your-bucket --delete
```

**Netlify:**
```bash
netlify deploy --prod
```

**Vercel:**
```bash
vercel --prod
```

See [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed hosting guides.

---

**Detailed Documentation:**
- [API_INTEGRATION.md](./API_INTEGRATION.md) - API integration guide
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Multi-platform deployment guide
- [TESTING.md](./TESTING.md) - Testing guide
- [Root README](../README.md) - Full project documentation
