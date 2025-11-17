# Load Testing with Artillery

Comprehensive load testing for Pixel Prompt backend API using Artillery.

## Overview

This directory contains Artillery configurations for load testing the Pixel Prompt API with realistic traffic patterns simulating 100 concurrent users.

**Purpose**: Verify system performance under load before production deployment.

## Prerequisites

### Install Artillery

```bash
# Install globally (recommended)
npm install -g artillery

# Or use via npx (no installation needed)
npx artillery --version
```

### Deploy to Environment

Load tests require a deployed backend:

```bash
# Deploy to staging (recommended for load testing)
./scripts/deploy.sh staging
```

## Test Configurations

### 1. Light Load Test (`artillery-config-light.yml`)

**Purpose**: Quick smoke test to verify API health

**Configuration**:
- Duration: 2 minutes
- Concurrent users: 10
- Total requests: ~120
- Estimated cost: $1-2

**Use Cases**:
- Quick API validation
- Testing after deployments
- Development environment testing

**Run**:
```bash
./scripts/run-loadtest.sh staging light
```

### 2. Full Load Test (`artillery-config.yml`)

**Purpose**: Comprehensive load test simulating production traffic

**Configuration**:
- Duration: 13 minutes total
  - Warm-up: 1 minute (10 users)
  - Ramp-up: 5 minutes (10 → 100 users)
  - Sustained: 5 minutes (100 users)
  - Cool-down: 2 minutes (100 → 0 users)
- Peak concurrent users: 100
- Total requests: ~1000+
- Estimated cost: $5-15

**Traffic Distribution**:
- 50% `/generate` (image generation)
- 30% `/status/{jobId}` (job status checks)
- 10% `/enhance` (prompt enhancement)
- 10% `/gallery/*` (gallery operations)

**Run**:
```bash
./scripts/run-loadtest.sh staging full
```

## Running Load Tests

### Quick Start

```bash
# Light test (recommended first)
./scripts/run-loadtest.sh staging light

# Full test (after light test succeeds)
./scripts/run-loadtest.sh staging full
```

### Manual Execution

```bash
# Set API endpoint
export API_ENDPOINT="https://your-api.execute-api.us-west-2.amazonaws.com/Prod"

# Run light test
cd scripts/loadtest
artillery run artillery-config-light.yml

# Run full test
artillery run artillery-config.yml --output results.json
artillery report results.json --output results.html
```

## Understanding Results

### Success Criteria

| Metric | Target | Status |
|--------|--------|--------|
| **Error Rate** | < 1% | Must pass |
| **P95 Response Time** | < 5000ms | Must pass |
| **P99 Response Time** | < 10000ms | Should pass |
| **Lambda Throttles** | 0 | Must pass |

### Key Metrics

**From Artillery Report**:
- **Scenarios**: Total users simulated
- **Requests**: Total API calls made
- **Response Times**: Min, Max, Median, P95, P99
- **Error Rate**: Percentage of failed requests
- **RPS**: Requests per second (throughput)

**From CloudWatch**:
- **Lambda Concurrent Executions**: Should peak at ~100
- **Lambda Throttles**: Should be 0 (indicates capacity issues)
- **Lambda Errors**: Should be minimal
- **API Gateway 4xx/5xx**: Should match Artillery errors

### Sample Output

```
=== Test Results Summary ===

Scenarios: 1000 / 1000 completed
Requests:  1250 total

HTTP Status Codes:
  200 (OK):            1230
  429 (Rate Limit):    10
  500 (Server Error):  5
  504 (Timeout):       5

Error Rate: 1.6%
  ✗ Above 1% target

Response Times:
  Min:    120ms
  Max:    8500ms
  Median: 450ms
  P95:    4200ms
  P99:    6800ms
```

## Troubleshooting

### High Error Rate (> 1%)

**Possible Causes**:
1. **Rate limiting triggered**: IP_LIMIT or GLOBAL_LIMIT exceeded
2. **Lambda cold starts**: Not enough warm containers
3. **AI provider rate limits**: External API limits hit
4. **Lambda timeout**: Image generation taking > 900s

**Solutions**:
```bash
# 1. Check rate limit configuration
aws lambda get-function-configuration \
  --function-name pixel-prompt-staging-function \
  --query 'Environment.Variables.{Global:GLOBAL_LIMIT,IP:IP_LIMIT}'

# 2. Increase reserved concurrency
# Update template.yaml: ReservedConcurrentExecutions: 20
./scripts/deploy.sh staging

# 3. Check CloudWatch logs for specific errors
aws logs filter-pattern /aws/lambda/pixel-prompt-staging-function \
  --filter-pattern "ERROR"
```

### Lambda Throttles

**Symptom**: CloudWatch shows Lambda throttles

**Cause**: Concurrent executions exceed reserved concurrency (default: 10)

**Solution**:
```yaml
# In backend/template.yaml
PixelPromptFunction:
  Type: AWS::Serverless::Function
  Properties:
    ReservedConcurrentExecutions: 50  # Increase from 10
```

### Slow Response Times (P95 > 5s)

**Investigation**:
```bash
# Check Lambda duration metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=pixel-prompt-staging-function \
  --start-time $(date -u -d '15 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 \
  --statistics Average,Maximum
```

**Common Causes**:
- Cold starts (implement Lambda Layers)
- Slow AI provider APIs (beyond our control)
- S3 retries (check S3 error rates)

### Cost Higher Than Expected

**Causes**:
- AI provider API calls (most expensive)
- Lambda invocations (moderate)
- S3 storage and requests (minimal)

**Cost Breakdown** (per 1000 requests):
- Lambda: ~$0.50
- AI API calls: ~$5-10 (varies by provider)
- S3: ~$0.05
- API Gateway: ~$0.03

**Reduce costs**:
- Use light test instead of full test
- Test in dev environment (fewer models)
- Mock AI providers for load testing

## Best Practices

### Before Load Testing

1. **Deploy to staging first**: Never load test production
2. **Run light test first**: Verify basic functionality
3. **Check AWS quotas**: Ensure account limits sufficient
4. **Set billing alerts**: Prevent unexpected costs
5. **Notify team**: If shared environment

### During Load Testing

1. **Monitor CloudWatch**: Watch metrics real-time
2. **Check costs**: Keep eye on AWS cost explorer
3. **Don't interrupt**: Let test complete for accurate results
4. **Save results**: Reports used for performance documentation

### After Load Testing

1. **Review HTML report**: Detailed breakdown of performance
2. **Update PERFORMANCE.md**: Document results
3. **Investigate failures**: If error rate > 1%
4. **Compare to previous tests**: Track performance over time
5. **Archive results**: Move to `loadtest-results/` directory

## Advanced Usage

### Custom Test Scenarios

Edit `artillery-config.yml` to customize:

```yaml
config:
  phases:
    # Custom load pattern
    - duration: 60
      arrivalRate: 20  # 20 users/second
      name: "Custom Phase"

scenarios:
  # Custom scenario
  - name: "My Test"
    weight: 100
    flow:
      - post:
          url: "/generate"
          json:
            prompt: "custom prompt"
```

### Environment Variables

Override defaults:

```bash
# Use specific API endpoint
export API_ENDPOINT="https://custom-api.example.com"

# Custom test data
artillery run artillery-config.yml \
  --variables '{"prompts":["test1","test2"]}'
```

### Plugins

Enhance Artillery with plugins:

```bash
# HTML reports
npm install -g artillery-plugin-html-report

# Metrics publishing
npm install -g artillery-plugin-cloudwatch

# Usage in config
config:
  plugins:
    html-report:
      output: report.html
    cloudwatch:
      namespace: "PixelPrompt/LoadTest"
```

## Cost Estimation

### Light Test (2 min, 10 users)
- Lambda: ~$0.10
- AI APIs: ~$0.50-1.00
- **Total**: ~$1-2

### Full Test (13 min, 100 users peak)
- Lambda: ~$2-3
- AI APIs: ~$5-10
- S3/API Gateway: ~$0.50
- **Total**: ~$8-15

**Note**: Costs vary significantly based on:
- AI provider pricing (most variable)
- Number of models configured
- Image generation settings (steps, guidance)

## Related Documentation

- [DEPLOYMENT.md](../../docs/DEPLOYMENT.md) - Deployment guide
- [PERFORMANCE.md](../../docs/PERFORMANCE.md) - Performance benchmarks
- [PRODUCTION_CHECKLIST.md](../../PRODUCTION_CHECKLIST.md) - Pre-deployment checklist

## Support

**Artillery Documentation**: https://www.artillery.io/docs

**Issues**:
1. Check CloudWatch logs first
2. Review Artillery output for errors
3. Consult troubleshooting section above
4. Open GitHub issue with logs and config
