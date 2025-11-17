# Testing Guide - Pixel Prompt Complete Backend

Comprehensive testing documentation for both unit and integration tests.

## Unit Tests

The backend includes 88 unit tests covering core modules and utilities.

### Running Unit Tests

```bash
cd backend
pip install -r requirements.txt -r tests/requirements.txt
python -m pytest tests/unit/ -v
```

### Test Coverage

- **Content Filtering** (16 tests): NSFW detection, keyword management, edge cases
- **Prompt Enhancement** (12 tests): OpenAI/Gemini providers, error handling, fallback behavior
- **Model Registry** (19 tests): Provider detection, model loading, 1-based indexing
- **Model Handlers** (11 tests): OpenAI, Google, Bedrock, Stability AI, BFL, Recraft
- **Rate Limiting** (9 tests): Global/IP limits, cleanup, whitelist bypass
- **Job Manager** (15 tests): Job lifecycle, status tracking, result aggregation
- **Storage Utilities** (6 tests): S3 upload, CloudFront URLs, gallery management

### Test Organization

```
backend/tests/
├── unit/
│   ├── conftest.py                    # Shared fixtures (mock S3, sample data)
│   ├── fixtures/
│   │   └── api_responses.py           # Mock API responses
│   ├── test_content_filter.py         # Content moderation tests
│   ├── test_enhance.py                # Prompt enhancement tests
│   ├── test_registry.py               # Model registry tests
│   ├── test_handlers.py               # Provider handler tests
│   ├── test_rate_limit.py             # Rate limiting tests
│   ├── test_job_manager.py            # Job management tests
│   └── test_storage.py                # S3 storage tests
└── integration/
    └── test_api_endpoints.py          # End-to-end API tests
```

### Running Specific Test Suites

```bash
# Run only content filter tests
pytest tests/unit/test_content_filter.py -v

# Run only tests that don't require S3 mocking
pytest tests/unit/test_content_filter.py tests/unit/test_enhance.py tests/unit/test_registry.py -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html
```

---

## Integration Testing

Comprehensive end-to-end testing plan for the deployed serverless backend.

### Prerequisites

Before testing, ensure:

- ✅ Backend deployed to AWS (`sam deploy` successful)
- ✅ API endpoint URL obtained from stack outputs
- ✅ At least 2 AI model API keys configured
- ✅ CloudFront distribution deployed (~15 minutes)
- ✅ S3 bucket created and accessible

Get your API endpoint:
```bash
export API_ENDPOINT=$(sam list stack-outputs --stack-name pixel-prompt-complete-dev | grep ApiEndpoint | awk '{print $2}')
echo "API Endpoint: $API_ENDPOINT"
```

## Test Suite

### Test 1: Health Check - Basic Connectivity

**Purpose**: Verify API Gateway and Lambda are responding

**Steps**:
```bash
# Should return 404 with proper CORS headers
curl -v $API_ENDPOINT/

# Check CORS headers in response:
# - Access-Control-Allow-Origin: *
# - Access-Control-Allow-Methods: GET, POST, OPTIONS
```

**Expected Result**:
- Status: `404`
- Body: `{"error": "Not found", "path": "/", "method": "GET"}`
- CORS headers present

**Pass/Fail**: ___________

---

### Test 2: Prompt Enhancement - Valid Request

**Purpose**: Verify prompt enhancement endpoint works

**Steps**:
```bash
curl -X POST $API_ENDPOINT/enhance \
  -H "Content-Type: application/json" \
  -d '{"prompt":"cat"}'
```

**Expected Result**:
- Status: `200`
- Body contains:
  - `"original": "cat"`
  - `"enhanced"`: A detailed prompt (longer than original)

**Pass/Fail**: ___________

---

### Test 3: Prompt Enhancement - Invalid Request

**Purpose**: Verify input validation

**Steps**:
```bash
# Empty prompt
curl -X POST $API_ENDPOINT/enhance \
  -H "Content-Type: application/json" \
  -d '{"prompt":""}'

# Should return 400: Prompt is required
```

**Expected Result**:
- Status: `400`
- Body: `{"error": "Prompt is required"}`

**Pass/Fail**: ___________

---

### Test 4: Image Generation - Basic Flow

**Purpose**: Verify complete image generation pipeline

**Steps**:
```bash
# 1. Create job
RESPONSE=$(curl -X POST $API_ENDPOINT/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "beautiful mountain sunset",
    "steps": 25,
    "guidance": 7,
    "ip": "1.2.3.4"
  }')

echo $RESPONSE

# 2. Extract job ID
JOB_ID=$(echo $RESPONSE | jq -r '.jobId')
echo "Job ID: $JOB_ID"

# 3. Poll for status (repeat every 10 seconds)
watch -n 10 "curl -s $API_ENDPOINT/status/$JOB_ID | jq"
```

**Expected Result**:

Initial response (< 1 second):
- Status: `200`
- Body: `{"jobId": "<uuid>", "message": "Job created successfully", "totalModels": <count>}`

Status polling:
- Initial: `"status": "pending"` or `"status": "in_progress"`
- After 1-2 minutes: Some models show `"status": "completed"`
- After 3-5 minutes: Most models completed or failed
- Final: `"status": "completed"` or `"status": "partial"`

Each completed model result includes:
- `"status": "completed"`
- `"imageKey": "group-images/..."`
- `"imageUrl": "https://<cloudfront>.cloudfront.net/..."`
- `"duration": <seconds>`

**Pass/Fail**: ___________

---

### Test 5: Image Retrieval via CloudFront

**Purpose**: Verify images are accessible via CloudFront CDN

**Steps**:
```bash
# Get image URL from status response
IMAGE_URL=$(curl -s $API_ENDPOINT/status/$JOB_ID | jq -r '.results[0].imageUrl')

echo "Image URL: $IMAGE_URL"

# Download image
curl -o test-image.png $IMAGE_URL

# Verify image file
file test-image.png
# Should show: PNG image data, 1024 x 1024, 8-bit/color RGBA

# Open in browser or viewer
# macOS: open test-image.png
# Linux: xdg-open test-image.png
```

**Expected Result**:
- Image downloads successfully (< 5 seconds)
- File is valid PNG format
- Image displays correctly
- Image matches the prompt

**Pass/Fail**: ___________

---

### Test 6: Rate Limiting - Global Limit

**Purpose**: Verify rate limiting prevents abuse

**Setup**: Set low limits for testing
```bash
sam deploy --parameter-overrides GlobalRateLimit=3 IPRateLimit=10
```

**Steps**:
```bash
# Send 5 requests rapidly
for i in {1..5}; do
  echo "Request $i:"
  curl -X POST $API_ENDPOINT/generate \
    -H "Content-Type: application/json" \
    -d "{\"prompt\":\"test $i\",\"ip\":\"1.2.3.4\"}" \
    | jq '.message // .error'
  sleep 1
done
```

**Expected Result**:
- Requests 1-3: Success (job created)
- Requests 4-5: `429` status with `"error": "Rate limit exceeded"`

**Pass/Fail**: ___________

---

### Test 7: Rate Limiting - IP Whitelist

**Purpose**: Verify IP whitelist bypasses rate limits

**Setup**:
```bash
sam deploy --parameter-overrides IPWhitelist=1.2.3.4
```

**Steps**:
```bash
# Send many requests from whitelisted IP
for i in {1..10}; do
  curl -X POST $API_ENDPOINT/generate \
    -H "Content-Type: application/json" \
    -d "{\"prompt\":\"test $i\",\"ip\":\"1.2.3.4\"}" \
    | jq '.message // .error'
done
```

**Expected Result**:
- All 10 requests succeed (no 429 errors)

**Pass/Fail**: ___________

---

### Test 8: Content Filtering - NSFW Detection

**Purpose**: Verify inappropriate content is blocked

**Steps**:
```bash
# Test with NSFW keyword
curl -X POST $API_ENDPOINT/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"nude person","ip":"1.2.3.4"}'
```

**Expected Result**:
- Status: `400`
- Body: `{"error": "Inappropriate content detected", "message": "Your prompt contains inappropriate content..."}`

**Pass/Fail**: ___________

---

### Test 9: Input Validation - Edge Cases

**Purpose**: Verify robust input validation

**Steps**:
```bash
# Missing prompt
curl -X POST $API_ENDPOINT/generate \
  -H "Content-Type: application/json" \
  -d '{"steps":25}'

# Prompt too long (>1000 chars)
LONG_PROMPT=$(python3 -c "print('a' * 1001)")
curl -X POST $API_ENDPOINT/generate \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"$LONG_PROMPT\",\"ip\":\"1.2.3.4\"}"

# Invalid JSON
curl -X POST $API_ENDPOINT/generate \
  -H "Content-Type: application/json" \
  -d 'invalid json'
```

**Expected Results**:
1. Missing prompt: `400` - "Prompt is required"
2. Long prompt: `400` - "Prompt too long"
3. Invalid JSON: `400` - "Invalid JSON in request body"

**Pass/Fail**: ___________

---

### Test 10: Job Status - Not Found

**Purpose**: Verify proper handling of invalid job IDs

**Steps**:
```bash
curl $API_ENDPOINT/status/invalid-job-id-12345
```

**Expected Result**:
- Status: `404`
- Body: `{"error": "Job not found", "jobId": "invalid-job-id-12345"}`

**Pass/Fail**: ___________

---

### Test 11: Parallel Model Execution

**Purpose**: Verify all configured models execute in parallel

**Steps**:
```bash
# Start job and track timing
START=$(date +%s)

RESPONSE=$(curl -X POST $API_ENDPOINT/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"sunset over ocean","steps":25,"ip":"1.2.3.4"}')

JOB_ID=$(echo $RESPONSE | jq -r '.jobId')

# Wait for completion
while true; do
  STATUS=$(curl -s $API_ENDPOINT/status/$JOB_ID | jq -r '.status')
  echo "Status: $STATUS"

  if [ "$STATUS" == "completed" ] || [ "$STATUS" == "partial" ] || [ "$STATUS" == "failed" ]; then
    break
  fi

  sleep 10
done

END=$(date +%s)
DURATION=$((END - START))

echo "Total duration: $DURATION seconds"
echo "Models configured: $(curl -s $API_ENDPOINT/status/$JOB_ID | jq '.totalModels')"
echo "Models completed: $(curl -s $API_ENDPOINT/status/$JOB_ID | jq '.completedModels')"
```

**Expected Result**:
- With 9 models, total duration should be ~60-120 seconds (not 9 × 60 seconds)
- This proves parallel execution (not sequential)
- Most models complete successfully (some may fail due to API issues)

**Pass/Fail**: ___________

---

### Test 12: S3 Job Status Storage

**Purpose**: Verify job status persists in S3

**Steps**:
```bash
# Get S3 bucket name
S3_BUCKET=$(sam list stack-outputs --stack-name pixel-prompt-complete-dev | grep S3BucketName | awk '{print $2}')

# Create a job
JOB_ID=$(curl -X POST $API_ENDPOINT/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"test","ip":"1.2.3.4"}' | jq -r '.jobId')

# Wait a moment for S3 write
sleep 2

# Check S3 directly
aws s3 cp s3://$S3_BUCKET/jobs/$JOB_ID/status.json - | jq
```

**Expected Result**:
- JSON file exists in S3
- Contains job metadata: jobId, status, createdAt, totalModels, results array

**Pass/Fail**: ___________

---

### Test 13: CloudWatch Logs Verification

**Purpose**: Verify logging and monitoring

**Steps**:
```bash
# View recent logs
sam logs --stack-name pixel-prompt-complete-dev --tail

# Or view in CloudWatch Console
# Check for:
# - "Initializing Lambda components..."
# - "Lambda initialization complete: X models configured"
# - Model execution logs
# - Rate limit checks
# - Content filter logs
```

**Expected Result**:
- Detailed logs for each request
- No unhandled exceptions
- Performance metrics visible

**Pass/Fail**: ___________

---

### Test 14: Multi-Provider Model Support

**Purpose**: Verify different AI providers work correctly

**Steps**:
```bash
# Check which providers are configured
curl -s $API_ENDPOINT/generate \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"prompt":"rainbow","ip":"1.2.3.4"}' | jq -r '.jobId' > job.txt

JOB_ID=$(cat job.txt)

# Wait for completion
sleep 120

# Check results by provider
curl -s $API_ENDPOINT/status/$JOB_ID | jq '.results[] | select(.status == "completed") | .model'
```

**Expected Result**:
- Multiple providers complete successfully:
  - OpenAI (DALL-E 3)
  - Google (Gemini 2.0 or Imagen 3.0)
  - AWS Bedrock (Nova Canvas or SD 3.5 Large)
  - Others (Stability AI, BFL, Recraft, etc.)

**Pass/Fail**: ___________

---

### Test 15: Cost and Performance Metrics

**Purpose**: Verify cost efficiency and performance

**Steps**:
```bash
# Run 10 test jobs
for i in {1..10}; do
  curl -X POST $API_ENDPOINT/generate \
    -H "Content-Type: application/json" \
    -d "{\"prompt\":\"test $i\",\"ip\":\"test-ip-$i\"}"
  sleep 5
done

# Check CloudWatch metrics
# - Lambda invocations
# - Lambda duration (should be < 2 minutes average)
# - Lambda errors (should be 0 or very low)

# Check costs in AWS Cost Explorer
# - Lambda charges
# - S3 charges
# - CloudFront charges
```

**Expected Result**:
- Average Lambda duration: 60-120 seconds per request
- Lambda memory usage: < 2GB
- No errors or throttling
- Cost per request: $0.05 - $0.20 (depending on models)

**Pass/Fail**: ___________

---

## Summary

Total Tests: 15
Passed: ___________
Failed: ___________

## Common Issues and Solutions

### Issue: "Module not found" errors in Lambda logs

**Solution**: Rebuild and redeploy
```bash
sam build
sam deploy
```

### Issue: CloudFront 403 errors on images

**Solution**: Wait for CloudFront distribution to fully deploy (~15 minutes after first deployment)

### Issue: Models failing with authentication errors

**Solution**: Verify API keys are correct in parameters
```bash
sam deploy --parameter-overrides Model1Key=correct-key-here
```

### Issue: Lambda timeout errors

**Solution**: Check if models are taking too long. Review individual model durations in job status.

### Issue: Rate limiting too aggressive

**Solution**: Increase limits
```bash
sam deploy --parameter-overrides GlobalRateLimit=5000 IPRateLimit=200
```

### Issue: S3 "Access Denied" errors

**Solution**: Verify Lambda has S3 permissions. Check IAM role in CloudFormation.

## Performance Benchmarks

After testing, record your benchmarks:

| Metric | Target | Actual |
|--------|--------|--------|
| API Response Time (POST /generate) | < 1s | _____ |
| Image Generation (per model) | 30-90s | _____ |
| Total Job Time (9 models) | 60-120s | _____ |
| CloudFront Image Load | < 2s | _____ |
| Lambda Cold Start | < 5s | _____ |
| Lambda Warm Start | < 1s | _____ |

## Next Steps

After successful testing:

1. ✅ Mark Phase 1 as complete
2. ✅ Proceed to Phase 2: Frontend Implementation
3. ✅ Configure frontend with API endpoint URL
4. ✅ Deploy to production environment

## Support

If tests fail:
- Check CloudWatch logs: `sam logs --stack-name <name> --tail`
- Review deployment guide: `backend/DEPLOYMENT.md`
- Check implementation plans: `docs/plans/Phase-1.md`

---

**Test completed by**: ___________

**Date**: ___________

**Environment**: ___________

**Notes**: ___________
