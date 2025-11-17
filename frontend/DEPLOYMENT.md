# Deployment Guide - Pixel Prompt Frontend

This guide covers deploying the Pixel Prompt frontend to various hosting platforms.

## Prerequisites

Before deploying, ensure:

1. **Backend is deployed** - You need the API Gateway URL from your AWS SAM deployment
2. **Environment configured** - `.env` file with `VITE_API_ENDPOINT` set
3. **Build succeeds** - Run `npm run build` locally to verify

## Quick Deployment

### 1. Configure Environment

Create `.env` file:

```bash
VITE_API_ENDPOINT=https://your-api-id.execute-api.us-west-2.amazonaws.com/Prod
```

### 2. Build for Production

```bash
npm install
npm run build
```

Output will be in `dist/` directory.

### 3. Deploy

Choose your hosting platform:

---

## AWS S3 + CloudFront (Recommended)

**Advantages:**
- Same AWS account as backend
- Fast global delivery via CloudFront
- Low cost (~$0.50-$2/month)
- Easy integration with backend

### Setup Steps

1. **Create S3 Bucket**

```bash
aws s3 mb s3://pixel-prompt-frontend-prod --region us-west-2
```

2. **Configure for Static Hosting**

```bash
aws s3 website s3://pixel-prompt-frontend-prod \
  --index-document index.html \
  --error-document index.html
```

3. **Deploy Build**

```bash
npm run build
aws s3 sync dist/ s3://pixel-prompt-frontend-prod --delete
```

4. **Create CloudFront Distribution**

```bash
# Via AWS Console or CLI
# Point origin to S3 bucket
# Set default root object: index.html
# Set error pages to return index.html for SPA routing
```

5. **Update CORS on Backend**

Update `backend/template.yaml` to allow your CloudFront domain:

```yaml
CorsConfiguration:
  AllowOrigins:
    - 'https://your-cloudfront-domain.cloudfront.net'
```

---

## Netlify

**Advantages:**
- Easiest deployment (drag & drop or Git integration)
- Automatic HTTPS
- Free tier available
- Built-in CI/CD

### Setup Steps

1. **Sign up at** [netlify.com](https://netlify.com)

2. **Deploy via CLI**

```bash
npm install -g netlify-cli
netlify login
netlify deploy --prod
```

Or **Deploy via Git:**

1. Push code to GitHub
2. Connect repository in Netlify
3. Set build command: `npm run build`
4. Set publish directory: `dist`
5. Add environment variable: `VITE_API_ENDPOINT`

3. **Configure Redirects**

Create `public/_redirects`:

```
/*    /index.html   200
```

---

## Vercel

**Advantages:**
- Optimized for Vite/React
- Zero-config deployment
- Edge network
- Free tier

### Setup Steps

1. **Install Vercel CLI**

```bash
npm install -g vercel
```

2. **Deploy**

```bash
vercel
```

3. **Set Environment Variables**

```bash
vercel env add VITE_API_ENDPOINT
# Enter your API endpoint when prompted
```

4. **Deploy Production**

```bash
vercel --prod
```

---

## Cloudflare Pages

**Advantages:**
- Free tier with unlimited bandwidth
- Global CDN
- Fast builds

### Setup Steps

1. **Connect Git Repository**

   - Go to [pages.cloudflare.com](https://pages.cloudflare.com)
   - Connect GitHub repo

2. **Configure Build Settings**

   - Build command: `npm run build`
   - Build output directory: `dist`
   - Environment variable: `VITE_API_ENDPOINT`

3. **Deploy**

   Automatic on every push to main branch

---

## Docker Deployment

For self-hosted or containerized deployments:

### Dockerfile

```dockerfile
FROM node:18-alpine as build

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
ARG VITE_API_ENDPOINT
ENV VITE_API_ENDPOINT=$VITE_API_ENDPOINT

RUN npm run build

# Production stage
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### nginx.conf

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Enable gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
}
```

### Build and Run

```bash
docker build --build-arg VITE_API_ENDPOINT=https://your-api.com -t pixel-prompt-frontend .
docker run -p 8080:80 pixel-prompt-frontend
```

---

## Post-Deployment

### 1. Verify Functionality

- [ ] Site loads correctly
- [ ] Can enter prompts
- [ ] Generate button triggers API calls
- [ ] Images load progressively
- [ ] Download works
- [ ] Modal expansion works
- [ ] Responsive on mobile

### 2. Performance Optimization

- Enable gzip/brotli compression
- Configure caching headers
- Monitor Core Web Vitals
- Test on various devices

### 3. Monitoring

- Set up error tracking (Sentry, LogRocket)
- Configure analytics (GA4, Plausible)
- Monitor API usage

### 4. Update Backend CORS

Ensure your backend allows requests from your frontend domain:

```yaml
# backend/template.yaml
CorsConfiguration:
  AllowOrigins:
    - 'https://your-frontend-domain.com'
    - 'https://www.your-frontend-domain.com'
```

Re-deploy backend after updating:

```bash
cd backend
sam build && sam deploy
```

---

## Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `VITE_API_ENDPOINT` | Yes | Backend API URL | `https://abc123.execute-api.us-west-2.amazonaws.com/Prod` |

---

## Troubleshooting

### Images not loading

- **Check CORS:** Ensure CloudFront domain is in backend CORS config
- **Check API endpoint:** Verify `VITE_API_ENDPOINT` is correct
- **Check Network tab:** Look for 403/404 errors

### API calls failing

- **CORS errors:** Update backend template.yaml
- **401/403 errors:** Check rate limiting settings
- **Timeout errors:** Increase Lambda timeout if needed

### Build fails

- **Clear cache:** `rm -rf node_modules dist .vite && npm install`
- **Check Node version:** Requires Node.js 18+
- **Check ESLint errors:** Run `npm run lint`

### Deployment issues

- **S3 permissions:** Ensure bucket policy allows CloudFront
- **Cache issues:** Invalidate CloudFront cache
- **Environment variables:** Verify they're set correctly

---

## Security Considerations

1. **API Keys:** Never commit `.env` files
2. **HTTPS only:** Always use HTTPS in production
3. **CSP headers:** Configure Content Security Policy
4. **Rate limiting:** Already handled by backend
5. **Content filtering:** Already handled by backend

---

## CI/CD Pipeline Example

### GitHub Actions

```yaml
name: Deploy Frontend

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Setup Node
      uses: actions/setup-node@v3
      with:
        node-version: 18

    - name: Install dependencies
      run: npm ci
      working-directory: ./frontend

    - name: Build
      env:
        VITE_API_ENDPOINT: ${{ secrets.VITE_API_ENDPOINT }}
      run: npm run build
      working-directory: ./frontend

    - name: Deploy to S3
      env:
        AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
        AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      run: |
        aws s3 sync dist/ s3://pixel-prompt-frontend-prod --delete
      working-directory: ./frontend

    - name: Invalidate CloudFront
      env:
        AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
        AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      run: |
        aws cloudfront create-invalidation --distribution-id ${{ secrets.CF_DISTRIBUTION_ID }} --paths "/*"
```

---

## Cost Estimates

### AWS S3 + CloudFront

- **S3 storage:** $0.023/GB/month (~$0.05 for typical site)
- **CloudFront:** $0.085/GB for first 10TB (~$0.50-$2/month for low traffic)
- **Total:** ~$1-3/month for small sites

### Netlify/Vercel/Cloudflare

- **Free tier:** 100GB bandwidth/month (usually sufficient)
- **Paid:** ~$20/month for pro features

---

## Support

For deployment issues:
1. Check this guide
2. Review frontend README.md
3. Check backend deployment logs
4. Verify environment variables

For production issues:
1. Check browser console
2. Check Network tab
3. Verify API is accessible
4. Check backend CloudWatch logs
