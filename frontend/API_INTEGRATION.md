# API Integration Guide

This document explains how the frontend integrates with the Pixel Prompt backend API.

## Overview

The frontend communicates with a serverless backend (AWS Lambda + API Gateway) that manages:
- Image generation across multiple AI models
- Job status polling
- Prompt enhancement
- Rate limiting and content filtering

## API Endpoints

Base URL set via environment variable: `VITE_API_ENDPOINT`

### 1. Generate Images

**Endpoint:** `POST /generate`

**Request:**
```json
{
  "prompt": "A serene landscape with mountains",
  "steps": 28,
  "guidance": 5,
  "control": 1.0
}
```

**Response:**
```json
{
  "jobId": "abc123-def456-ghi789",
  "status": "in_progress",
  "message": "Generation started"
}
```

**Frontend Implementation:**

```javascript
import { generateImages } from './api/client';

const response = await generateImages(prompt, {
  steps: 28,
  guidance: 5,
  control: 1.0
});

// Start polling for status
const jobId = response.jobId;
```

**Error Responses:**

- `400 Bad Request` - Invalid parameters or filtered content
- `429 Too Many Requests` - Rate limit exceeded
- `500 Server Error` - Internal error

---

### 2. Get Job Status

**Endpoint:** `GET /status/{jobId}`

**Response:**
```json
{
  "jobId": "abc123-def456-ghi789",
  "status": "in_progress",
  "completedModels": 3,
  "totalModels": 9,
  "results": [
    {
      "model": "DALL-E 3",
      "status": "completed",
      "imageUrl": "group-images/abc123/0.json",
      "completedAt": "2025-11-15T10:30:45Z"
    },
    {
      "model": "Gemini 2.0",
      "status": "in_progress"
    }
  ]
}
```

**Status Values:**

- `in_progress` - Job is running
- `completed` - All models succeeded
- `partial` - Some models completed, some failed
- `failed` - All models failed

**Frontend Implementation:**

```javascript
import useJobPolling from './hooks/useJobPolling';

const { jobStatus, isPolling, error } = useJobPolling(jobId, 2000);

// jobStatus updates every 2 seconds until complete
```

---

### 3. Enhance Prompt

**Endpoint:** `POST /enhance`

**Request:**
```json
{
  "prompt": "sunset"
}
```

**Response:**
```json
{
  "short_prompt": "A beautiful sunset over the ocean with vibrant orange and pink hues",
  "long_prompt": "A breathtaking sunset over the ocean with vibrant orange, pink, and purple hues reflecting on the calm water. Silhouettes of palm trees frame the scene, while seagulls fly across the colorful sky. The sun is positioned just above the horizon, creating a golden path across the water."
}
```

**Frontend Implementation:**

```javascript
import { enhancePrompt } from './api/client';

const enhanced = await enhancePrompt(currentPrompt);
console.log(enhanced.short_prompt);
console.log(enhanced.long_prompt);
```

---

## Image Loading

Images are stored in S3 and served via CloudFront:

### Image URL Structure

```
https://{cloudFrontDomain}/group-images/{jobId}/{modelIndex}.json
```

### Image JSON Format

```json
{
  "output": "base64-encoded-image-data",
  "model": "DALL-E 3",
  "prompt": "original prompt text"
}
```

### Frontend Implementation

```javascript
import { fetchImageFromS3, base64ToBlobUrl } from './utils/imageHelpers';

// Fetch image JSON
const imageData = await fetchImageFromS3(imageUrl, cloudFrontDomain);

// Convert base64 to blob URL
const blobUrl = base64ToBlobUrl(imageData.output);

// Use in img tag
<img src={blobUrl} alt="Generated image" />

// Clean up when done
revokeBlobUrl(blobUrl);
```

---

## API Client Architecture

### Client Configuration

**File:** `src/api/config.js`

```javascript
export const API_BASE_URL = import.meta.env.VITE_API_ENDPOINT;

export const API_ROUTES = {
  GENERATE: '/generate',
  STATUS: '/status',
  ENHANCE: '/enhance',
};

export const REQUEST_TIMEOUT = 30000; // 30 seconds
```

### Error Handling

**File:** `src/api/client.js`

The API client includes:

1. **Timeout handling** (30 seconds)
2. **Retry logic** (3 retries with exponential backoff)
3. **Error parsing** (extracts error messages from responses)

```javascript
try {
  const response = await generateImages(prompt, params);
} catch (error) {
  if (error.status === 429) {
    // Rate limit exceeded
  } else if (error.code === 'TIMEOUT') {
    // Request timed out
  } else {
    // Other error
  }
}
```

### Retry Logic

Network errors trigger automatic retry:

- **Attempt 1:** Immediate
- **Attempt 2:** After 1s delay
- **Attempt 3:** After 2s delay
- **Attempt 4:** After 4s delay

HTTP errors (4xx, 5xx) are **not retried**.

---

## Job Polling

**File:** `src/hooks/useJobPolling.js`

### Configuration

```javascript
const DEFAULT_INTERVAL = 2000; // 2 seconds
const TIMEOUT_DURATION = 300000; // 5 minutes
const MAX_CONSECUTIVE_ERRORS = 5;
```

### Behavior

1. **Poll every 2 seconds** while job is in progress
2. **Stop polling** when job reaches terminal state (`completed`, `partial`, `failed`)
3. **Exponential backoff** on errors (2s → 4s → 8s)
4. **Stop after 5 consecutive errors** or 5-minute timeout

### Usage

```javascript
const { jobStatus, isPolling, error } = useJobPolling(jobId, 2000);

useEffect(() => {
  if (jobStatus?.status === 'completed') {
    console.log('All images generated!');
  }
}, [jobStatus]);
```

---

## State Management

**File:** `src/context/AppContext.jsx`

### Global State

```javascript
{
  // Current generation
  currentJob: { jobId, status },
  prompt: "user's prompt",
  parameters: { steps, guidance, control },

  // Results
  generatedImages: Array(9).fill(null),

  // UI state
  isGenerating: false,

  // Gallery
  selectedGallery: null
}
```

### State Updates

```javascript
const { setPrompt, updateParameter, setIsGenerating } = useApp();

// Update prompt
setPrompt("new prompt");

// Update parameter
updateParameter('steps', 35);

// Start generation
setIsGenerating(true);
```

---

## Rate Limiting

Backend enforces:

- **Global limit:** 1000 requests/hour
- **Per-IP limit:** 50 requests/day

### Handling Rate Limits

```javascript
catch (error) {
  if (error.status === 429) {
    setErrorMessage('Rate limit exceeded. Please try again later.');
  }
}
```

Users see friendly error message.

---

## Content Filtering

Backend filters inappropriate prompts.

### Handling Filtered Content

```javascript
catch (error) {
  if (error.status === 400 && error.message?.includes('filter')) {
    setErrorMessage('Prompt contains inappropriate content. Please try a different prompt.');
  }
}
```

---

## CORS Configuration

Backend must allow frontend origin.

### Backend Configuration

**File:** `backend/template.yaml`

```yaml
CorsConfiguration:
  AllowOrigins:
    - 'https://your-frontend-domain.com'
  AllowHeaders:
    - Content-Type
    - Authorization
  AllowMethods:
    - GET
    - POST
    - OPTIONS
  MaxAge: 86400
```

### Testing CORS

```javascript
// Should succeed
fetch('https://api.example.com/generate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ prompt: 'test' })
});
```

If CORS fails:
1. Check browser console for CORS error
2. Verify `AllowOrigins` includes your domain
3. Redeploy backend after changes

---

## Environment Setup

### Development

**File:** `frontend/.env`

```bash
VITE_API_ENDPOINT=https://local-api-gateway-url.com/Prod
```

### Production

Set via hosting platform:

**Netlify:**
```bash
netlify env:set VITE_API_ENDPOINT "https://prod-api.com/Prod"
```

**Vercel:**
```bash
vercel env add VITE_API_ENDPOINT
```

**AWS S3:**
Build with environment variable:
```bash
VITE_API_ENDPOINT=https://prod-api.com/Prod npm run build
```

---

## Testing API Integration

### Manual Testing

1. **Generate images:**
   - Enter prompt
   - Click "Generate Images"
   - Watch progress bar
   - Verify images appear

2. **Enhance prompt:**
   - Enter short prompt
   - Click "Enhance Prompt"
   - Verify enhanced versions

3. **Download images:**
   - Hover over completed image
   - Click download button
   - Verify file downloads

### Automated Testing

```javascript
// Test API client
import { generateImages } from './api/client';

test('generateImages returns jobId', async () => {
  const response = await generateImages('test prompt', {
    steps: 28,
    guidance: 5
  });

  expect(response).toHaveProperty('jobId');
  expect(response.status).toBe('in_progress');
});
```

---

## Performance Optimization

### API Calls

- **Debounce prompt input** (prevent API spam)
- **Cancel pending requests** on unmount
- **Cache enhanced prompts** (avoid redundant calls)

### Image Loading

- **Progressive loading** (show images as they complete)
- **Lazy loading** (images load off-screen)
- **Blob URL cleanup** (prevent memory leaks)

### Polling

- **Stop polling** when job complete
- **Exponential backoff** on errors
- **Cleanup intervals** on unmount

---

## Debugging

### Browser DevTools

1. **Network tab:**
   - Check request/response
   - Verify CORS headers
   - Check status codes

2. **Console:**
   - API errors logged automatically
   - Check for CORS errors
   - Verify environment variables

### Common Issues

**Issue:** API calls return 403
- **Fix:** Check CORS configuration

**Issue:** Images don't load
- **Fix:** Verify CloudFront domain accessible

**Issue:** Polling never stops
- **Fix:** Check cleanup in useJobPolling

**Issue:** Rate limited quickly
- **Fix:** Check IP whitelist or increase limits

---

## API Versioning

Currently: **v1** (implicit)

Future versions may include:
- `/v2/generate`
- `/v2/status`

Frontend will support both during migration period.

---

## Security Considerations

1. **Never expose API keys** in frontend code
2. **Use HTTPS** in production
3. **Validate responses** before rendering
4. **Sanitize user input** (backend handles this)
5. **Implement CSP headers** on hosting

---

## Support

For API integration issues:
1. Check this guide
2. Review `src/api/client.js`
3. Check backend CloudWatch logs
4. Verify CORS configuration
