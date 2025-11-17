#!/usr/bin/env bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default values
ENVIRONMENT="${1:-staging}"
TEST_TYPE="${2:-light}"

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    echo -e "${RED}Error: Invalid environment '$ENVIRONMENT'${NC}"
    echo "Usage: $0 [dev|staging|prod] [light|full]"
    exit 1
fi

# Validate test type
if [[ ! "$TEST_TYPE" =~ ^(light|full)$ ]]; then
    echo -e "${RED}Error: Invalid test type '$TEST_TYPE'${NC}"
    echo "Usage: $0 [dev|staging|prod] [light|full]"
    exit 1
fi

echo -e "${GREEN}=== Artillery Load Test ===${NC}"
echo -e "Environment: ${YELLOW}$ENVIRONMENT${NC}"
echo -e "Test Type:   ${YELLOW}$TEST_TYPE${NC}"
echo ""

# Check if Artillery is installed
if ! command -v artillery &> /dev/null; then
    echo -e "${RED}Error: Artillery not found${NC}"
    echo "Install with: npm install -g artillery"
    echo "Or use npx: npx artillery run ..."
    exit 1
fi

echo -e "${GREEN}✓ Artillery found: $(artillery --version)${NC}"
echo ""

# Get API endpoint from environment
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
STACK_NAME="pixel-prompt-$ENVIRONMENT"

echo "Getting API endpoint from CloudFormation..."
export API_ENDPOINT=$(sam list stack-outputs --stack-name "$STACK_NAME" 2>/dev/null | \
    grep "ApiEndpoint" | awk '{print $2}' || echo "")

if [ -z "$API_ENDPOINT" ]; then
    echo -e "${RED}Error: Could not get API endpoint from CloudFormation${NC}"
    echo "Make sure you've deployed to $ENVIRONMENT first: ./scripts/deploy.sh $ENVIRONMENT"
    echo ""
    echo "Or set API_ENDPOINT manually:"
    echo "  export API_ENDPOINT=https://your-api.execute-api.us-west-2.amazonaws.com/Prod"
    echo "  $0 $ENVIRONMENT $TEST_TYPE"
    exit 1
fi

echo -e "${GREEN}✓ API Endpoint: $API_ENDPOINT${NC}"
echo ""

# Cost warning
if [ "$TEST_TYPE" == "full" ]; then
    echo -e "${YELLOW}⚠ WARNING: Full load test will make ~1000+ API requests${NC}"
    echo -e "${YELLOW}  This will trigger Lambda invocations and AI API calls${NC}"
    echo -e "${YELLOW}  Estimated cost: \$5-15 depending on AI provider pricing${NC}"
    echo ""
    echo -e "${YELLOW}  Test duration: ~13 minutes (warm-up + ramp + sustained + cool-down)${NC}"
else
    echo -e "${YELLOW}Light load test: ~120 requests over 2 minutes${NC}"
    echo -e "${YELLOW}Estimated cost: ~\$1-2${NC}"
fi

echo ""
read -p "Continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Load test cancelled"
    exit 0
fi

# Select config file
if [ "$TEST_TYPE" == "full" ]; then
    CONFIG_FILE="$SCRIPT_DIR/loadtest/artillery-config.yml"
else
    CONFIG_FILE="$SCRIPT_DIR/loadtest/artillery-config-light.yml"
fi

# Create results directory
RESULTS_DIR="$SCRIPT_DIR/../loadtest-results"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REPORT_FILE="$RESULTS_DIR/artillery-report-$TEST_TYPE-$TIMESTAMP"

echo ""
echo -e "${YELLOW}Starting load test...${NC}"
echo "API Endpoint: $API_ENDPOINT"
echo "Config: $CONFIG_FILE"
echo "Report: $REPORT_FILE"
echo ""

# Run Artillery
artillery run \
    "$CONFIG_FILE" \
    --output "$REPORT_FILE.json" \
    2>&1 | tee "$REPORT_FILE.log"

EXIT_CODE=${PIPESTATUS[0]}

echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ Load test completed${NC}"
else
    echo -e "${RED}✗ Load test failed with exit code $EXIT_CODE${NC}"
fi

echo ""

# Generate HTML report
echo -e "${YELLOW}Generating HTML report...${NC}"

if artillery report "$REPORT_FILE.json" --output "$REPORT_FILE.html" 2>/dev/null; then
    echo -e "${GREEN}✓ HTML report generated${NC}"
else
    echo -e "${YELLOW}⚠ Could not generate HTML report (install artillery-plugin-html-report)${NC}"
    echo "  npm install -g artillery-plugin-html-report"
fi

echo ""

# Parse results from JSON (basic parsing)
if [ -f "$REPORT_FILE.json" ]; then
    echo -e "${YELLOW}=== Test Results Summary ===${NC}"
    echo ""

    # Extract key metrics using grep (works without jq)
    if grep -q "aggregate" "$REPORT_FILE.json"; then
        echo "Parsing results..."

        # Count total scenarios
        SCENARIOS_TOTAL=$(grep -o '"scenariosCreated":[0-9]*' "$REPORT_FILE.json" | tail -1 | cut -d':' -f2)
        SCENARIOS_COMPLETED=$(grep -o '"scenariosCompleted":[0-9]*' "$REPORT_FILE.json" | tail -1 | cut -d':' -f2)

        # Count requests
        REQUESTS_COMPLETED=$(grep -o '"requestsCompleted":[0-9]*' "$REPORT_FILE.json" | tail -1 | cut -d':' -f2)

        # Count errors
        CODES_200=$(grep -o '"200":[0-9]*' "$REPORT_FILE.json" | head -1 | cut -d':' -f2 || echo "0")
        CODES_429=$(grep -o '"429":[0-9]*' "$REPORT_FILE.json" | head -1 | cut -d':' -f2 || echo "0")
        CODES_500=$(grep -o '"500":[0-9]*' "$REPORT_FILE.json" | head -1 | cut -d':' -f2 || echo "0")
        CODES_504=$(grep -o '"504":[0-9]*' "$REPORT_FILE.json" | head -1 | cut -d':' -f2 || echo "0")

        echo "  Scenarios: $SCENARIOS_COMPLETED / $SCENARIOS_TOTAL completed"
        echo "  Requests:  $REQUESTS_COMPLETED total"
        echo ""
        echo "  HTTP Status Codes:"
        echo "    200 (OK):            $CODES_200"
        echo "    429 (Rate Limit):    $CODES_429"
        echo "    500 (Server Error):  $CODES_500"
        echo "    504 (Timeout):       $CODES_504"
        echo ""

        # Calculate error rate
        if [ "$REQUESTS_COMPLETED" -gt 0 ]; then
            ERRORS=$(($CODES_429 + $CODES_500 + $CODES_504))
            ERROR_RATE=$(echo "scale=2; ($ERRORS / $REQUESTS_COMPLETED) * 100" | bc)
            echo "  Error Rate: $ERROR_RATE%"

            if (( $(echo "$ERROR_RATE < 1" | bc -l) )); then
                echo -e "    ${GREEN}✓ Below 1% target${NC}"
            else
                echo -e "    ${RED}✗ Above 1% target${NC}"
            fi
        fi
    fi
fi

echo ""
echo -e "${YELLOW}Results saved to:${NC}"
echo "  JSON: $REPORT_FILE.json"
echo "  Log:  $REPORT_FILE.log"
if [ -f "$REPORT_FILE.html" ]; then
    echo "  HTML: $REPORT_FILE.html"
fi

echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Review full HTML report: open $REPORT_FILE.html"
echo "2. Check CloudWatch metrics for Lambda and API Gateway"
echo "3. Update docs/PERFORMANCE.md with results"
echo "4. If errors > 1%, investigate CloudWatch logs"
echo ""
echo -e "${YELLOW}CloudWatch Commands:${NC}"
echo "  # View Lambda logs"
echo "  aws logs tail /aws/lambda/$STACK_NAME-function --follow"
echo ""
echo "  # Lambda metrics (last 15 minutes)"
echo "  aws cloudwatch get-metric-statistics \\"
echo "    --namespace AWS/Lambda \\"
echo "    --metric-name ConcurrentExecutions \\"
echo "    --dimensions Name=FunctionName,Value=$STACK_NAME-function \\"
echo "    --start-time $(date -u -d '15 minutes ago' +%Y-%m-%dT%H:%M:%S) \\"
echo "    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \\"
echo "    --period 60 \\"
echo "    --statistics Maximum"
echo ""

exit $EXIT_CODE
