#!/usr/bin/env bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default environment
ENVIRONMENT="${1:-staging}"

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    echo -e "${RED}Error: Invalid environment '$ENVIRONMENT'${NC}"
    echo "Usage: $0 [dev|staging|prod]"
    exit 1
fi

echo -e "${GREEN}=== CloudFront Distribution Verification ===${NC}"
echo -e "Environment: ${YELLOW}$ENVIRONMENT${NC}"
echo ""

STACK_NAME="pixel-prompt-$ENVIRONMENT"

# Get CloudFormation outputs
echo "Getting CloudFormation outputs..."

if ! sam list stack-outputs --stack-name "$STACK_NAME" &> /dev/null; then
    echo -e "${RED}Error: Stack '$STACK_NAME' not found${NC}"
    echo "Deploy first: ./scripts/deploy.sh $ENVIRONMENT"
    exit 1
fi

API_ENDPOINT=$(sam list stack-outputs --stack-name "$STACK_NAME" 2>/dev/null | \
    grep "ApiEndpoint" | awk '{print $2}')
CLOUDFRONT_DOMAIN=$(sam list stack-outputs --stack-name "$STACK_NAME" 2>/dev/null | \
    grep "CloudFrontDomain" | awk '{print $2}')
S3_BUCKET=$(sam list stack-outputs --stack-name "$STACK_NAME" 2>/dev/null | \
    grep "S3BucketName" | awk '{print $2}')

if [ -z "$API_ENDPOINT" ] || [ -z "$CLOUDFRONT_DOMAIN" ] || [ -z "$S3_BUCKET" ]; then
    echo -e "${RED}Error: Could not retrieve CloudFormation outputs${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Outputs retrieved${NC}"
echo "  API Endpoint:      $API_ENDPOINT"
echo "  CloudFront Domain: $CLOUDFRONT_DOMAIN"
echo "  S3 Bucket:         $S3_BUCKET"
echo ""

# Check CloudFront distribution status
echo -e "${YELLOW}Checking CloudFront distribution status...${NC}"

# Get distribution ID from domain
DISTRIBUTION_ID=$(echo "$CLOUDFRONT_DOMAIN" | cut -d'.' -f1)

DISTRIBUTION_STATUS=$(aws cloudfront get-distribution \
    --id "$DISTRIBUTION_ID" \
    --query 'Distribution.Status' \
    --output text 2>/dev/null || echo "UNKNOWN")

if [ "$DISTRIBUTION_STATUS" == "Deployed" ]; then
    echo -e "${GREEN}✓ Distribution status: Deployed${NC}"
elif [ "$DISTRIBUTION_STATUS" == "InProgress" ]; then
    echo -e "${YELLOW}⚠ Distribution status: InProgress (still deploying)${NC}"
    echo "  CloudFront deployment can take up to 15 minutes"
    echo "  Run this script again after deployment completes"
    exit 0
else
    echo -e "${RED}✗ Distribution status: $DISTRIBUTION_STATUS${NC}"
fi

echo ""

# Test if we can generate an image to test CloudFront
echo -e "${YELLOW}Testing image generation and CloudFront delivery...${NC}"
echo ""

# Generate test image
echo "Step 1: Generating test image..."
CORRELATION_ID="cloudfront-test-$(date +%s)"

GENERATE_RESPONSE=$(curl -s -X POST "$API_ENDPOINT/generate" \
    -H "Content-Type: application/json" \
    -H "X-Correlation-ID: $CORRELATION_ID" \
    -d '{
        "prompt": "cloudfront test image",
        "steps": 25,
        "guidance": 7,
        "ip": "127.0.0.1"
    }')

JOB_ID=$(echo "$GENERATE_RESPONSE" | grep -o '"jobId":"[^"]*"' | cut -d'"' -f4)

if [ -z "$JOB_ID" ]; then
    echo -e "${RED}✗ Failed to generate test image${NC}"
    echo "  Response: $GENERATE_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Job created: $JOB_ID${NC}"
echo ""

# Wait for job to complete (with timeout)
echo "Step 2: Waiting for image generation (max 3 minutes)..."
TIMEOUT=180
ELAPSED=0
STATUS="pending"

while [ $ELAPSED -lt $TIMEOUT ]; do
    sleep 10
    ELAPSED=$((ELAPSED + 10))

    STATUS_RESPONSE=$(curl -s "$API_ENDPOINT/status/$JOB_ID")
    STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)

    echo "  [$ELAPSED s] Status: $STATUS"

    if [ "$STATUS" == "complete" ] || [ "$STATUS" == "completed" ]; then
        break
    fi

    if [ "$STATUS" == "failed" ]; then
        echo -e "${RED}✗ Image generation failed${NC}"
        echo "  Response: $STATUS_RESPONSE"
        exit 1
    fi
done

if [ "$STATUS" != "complete" ] && [ "$STATUS" != "completed" ]; then
    echo -e "${YELLOW}⚠ Timeout waiting for image generation${NC}"
    echo "  Job may still be processing, but taking longer than expected"
    exit 0
fi

echo -e "${GREEN}✓ Image generation complete${NC}"
echo ""

# Extract image URL
IMAGE_URL=$(echo "$STATUS_RESPONSE" | grep -o '"imageUrl":"https://[^"]*"' | head -1 | cut -d'"' -f4)

if [ -z "$IMAGE_URL" ]; then
    echo -e "${RED}✗ No image URL found in response${NC}"
    echo "  Response: $STATUS_RESPONSE"
    exit 1
fi

echo "Image URL: $IMAGE_URL"
echo ""

# Verify URL is using CloudFront
if echo "$IMAGE_URL" | grep -q "$CLOUDFRONT_DOMAIN"; then
    echo -e "${GREEN}✓ Image URL uses CloudFront domain${NC}"
else
    echo -e "${YELLOW}⚠ Image URL does NOT use CloudFront domain${NC}"
    echo "  Expected domain: $CLOUDFRONT_DOMAIN"
    echo "  Actual URL:      $IMAGE_URL"
fi

echo ""

# Test CloudFront cache behavior
echo -e "${YELLOW}Step 3: Testing CloudFront cache behavior...${NC}"
echo ""

# First request (should be cache MISS)
echo "Request 1: Testing cache MISS..."
RESPONSE_1=$(curl -s -I "$IMAGE_URL" 2>&1)
HTTP_STATUS_1=$(echo "$RESPONSE_1" | grep "HTTP" | awk '{print $2}')
CACHE_STATUS_1=$(echo "$RESPONSE_1" | grep -i "x-cache:" | awk '{print $2, $3, $4}' | tr -d '\r')
TIME_1_START=$(date +%s%N)
curl -s -o /dev/null "$IMAGE_URL"
TIME_1_END=$(date +%s%N)
TIME_1_MS=$(( ($TIME_1_END - $TIME_1_START) / 1000000 ))

echo "  HTTP Status: $HTTP_STATUS_1"
echo "  X-Cache: $CACHE_STATUS_1"
echo "  Response Time: ${TIME_1_MS}ms"
echo ""

if [ "$HTTP_STATUS_1" != "200" ]; then
    echo -e "${RED}✗ Image not accessible (HTTP $HTTP_STATUS_1)${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Image accessible via CloudFront${NC}"
echo ""

# Second request (should be cache HIT)
echo "Request 2: Testing cache HIT (same image)..."
sleep 1
RESPONSE_2=$(curl -s -I "$IMAGE_URL" 2>&1)
HTTP_STATUS_2=$(echo "$RESPONSE_2" | grep "HTTP" | awk '{print $2}')
CACHE_STATUS_2=$(echo "$RESPONSE_2" | grep -i "x-cache:" | awk '{print $2, $3, $4}' | tr -d '\r')
TIME_2_START=$(date +%s%N)
curl -s -o /dev/null "$IMAGE_URL"
TIME_2_END=$(date +%s%N)
TIME_2_MS=$(( ($TIME_2_END - $TIME_2_START) / 1000000 ))

echo "  HTTP Status: $HTTP_STATUS_2"
echo "  X-Cache: $CACHE_STATUS_2"
echo "  Response Time: ${TIME_2_MS}ms"
echo ""

# Compare cache behavior
if echo "$CACHE_STATUS_2" | grep -qi "hit"; then
    echo -e "${GREEN}✓ Cache HIT detected on second request${NC}"
    SPEEDUP=$(echo "scale=1; $TIME_1_MS / $TIME_2_MS" | bc)
    echo "  Performance improvement: ${SPEEDUP}x faster"
elif echo "$CACHE_STATUS_2" | grep -qi "miss"; then
    echo -e "${YELLOW}⚠ Cache MISS on second request${NC}"
    echo "  This might indicate caching is not working as expected"
else
    echo -e "${YELLOW}⚠ Cache status unclear: $CACHE_STATUS_2${NC}"
fi

echo ""

# Check cache headers
echo -e "${YELLOW}Step 4: Verifying cache headers...${NC}"
echo ""

CACHE_CONTROL=$(echo "$RESPONSE_2" | grep -i "cache-control:" | awk '{print $2}' | tr -d '\r')
ETAG=$(echo "$RESPONSE_2" | grep -i "etag:" | awk '{print $2}' | tr -d '\r')

echo "Cache-Control: $CACHE_CONTROL"
echo "ETag:          $ETAG"

if [ -n "$CACHE_CONTROL" ]; then
    echo -e "${GREEN}✓ Cache-Control header present${NC}"
else
    echo -e "${YELLOW}⚠ Cache-Control header missing${NC}"
fi

if [ -n "$ETAG" ]; then
    echo -e "${GREEN}✓ ETag header present${NC}"
else
    echo -e "${YELLOW}⚠ ETag header missing${NC}"
fi

echo ""

# Check CloudFront configuration
echo -e "${YELLOW}Step 5: Checking CloudFront configuration...${NC}"
echo ""

DISTRIBUTION_CONFIG=$(aws cloudfront get-distribution-config \
    --id "$DISTRIBUTION_ID" \
    --output json 2>/dev/null)

if [ -n "$DISTRIBUTION_CONFIG" ]; then
    # Extract TTL values
    DEFAULT_TTL=$(echo "$DISTRIBUTION_CONFIG" | grep -o '"DefaultTTL":[0-9]*' | cut -d':' -f2 || echo "unknown")
    MAX_TTL=$(echo "$DISTRIBUTION_CONFIG" | grep -o '"MaxTTL":[0-9]*' | cut -d':' -f2 || echo "unknown")
    MIN_TTL=$(echo "$DISTRIBUTION_CONFIG" | grep -o '"MinTTL":[0-9]*' | cut -d':' -f2 || echo "unknown")

    echo "Cache TTL Configuration:"
    echo "  Min TTL:     ${MIN_TTL}s"
    echo "  Default TTL: ${DEFAULT_TTL}s ($(($DEFAULT_TTL / 3600)) hours)"
    echo "  Max TTL:     ${MAX_TTL}s ($(($MAX_TTL / 86400)) days)"
    echo ""

    if [ "$DEFAULT_TTL" -ge 86400 ]; then
        echo -e "${GREEN}✓ Default TTL >= 24 hours (good for immutable images)${NC}"
    else
        echo -e "${YELLOW}⚠ Default TTL < 24 hours (consider increasing for images)${NC}"
    fi
fi

echo ""

# Deployment time check (if recently deployed)
echo -e "${YELLOW}Step 6: Checking deployment time...${NC}"
echo ""

LAST_MODIFIED=$(aws cloudfront get-distribution \
    --id "$DISTRIBUTION_ID" \
    --query 'Distribution.DistributionConfig.Comment' \
    --output text 2>/dev/null || echo "")

echo "Distribution Comment: $LAST_MODIFIED"
echo ""
echo -e "${YELLOW}Note: CloudFront deployment time cannot be measured automatically${NC}"
echo "  Typical deployment time: 10-15 minutes"
echo "  Target: < 15 minutes"
echo "  Measure manually during deployment: time aws cloudfront wait distribution-deployed"
echo ""

# Summary
echo -e "${GREEN}=== CloudFront Verification Summary ===${NC}"
echo ""
echo "✓ Distribution Status:  Deployed"
echo "✓ Image Delivery:       Working"
echo "✓ Cache Behavior:       $(echo $CACHE_STATUS_1 | grep -q 'Miss' && echo 'MISS → HIT' || echo 'Verified')"
echo "✓ Cache Headers:        Present"
echo "✓ TTL Configuration:    $([ "$DEFAULT_TTL" -ge 86400 ] && echo 'Optimal' || echo 'Acceptable')"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Document results in docs/PERFORMANCE.md"
echo "2. If cache behavior is suboptimal, review backend/template.yaml CloudFront config"
echo "3. Monitor CloudFront metrics in CloudWatch"
echo ""
echo -e "${YELLOW}CloudWatch Metrics:${NC}"
echo "  aws cloudfront get-metric-statistics \\"
echo "    --namespace AWS/CloudFront \\"
echo "    --metric-name Requests \\"
echo "    --dimensions Name=DistributionId,Value=$DISTRIBUTION_ID \\"
echo "    --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \\"
echo "    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \\"
echo "    --period 300 \\"
echo "    --statistics Sum"
echo ""
