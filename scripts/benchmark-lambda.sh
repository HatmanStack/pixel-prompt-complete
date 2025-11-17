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

echo -e "${GREEN}=== Lambda Cold Start Benchmark ===${NC}"
echo -e "Environment: ${YELLOW}$ENVIRONMENT${NC}"
echo ""

# Get stack info
STACK_NAME="pixel-prompt-$ENVIRONMENT"
FUNCTION_NAME="$STACK_NAME-function"

echo "Checking Lambda function exists..."
if ! aws lambda get-function --function-name "$FUNCTION_NAME" &> /dev/null; then
    echo -e "${RED}Error: Lambda function '$FUNCTION_NAME' not found${NC}"
    echo "Make sure you've deployed to $ENVIRONMENT first: ./scripts/deploy.sh $ENVIRONMENT"
    exit 1
fi

echo -e "${GREEN}✓ Function found: $FUNCTION_NAME${NC}"
echo ""

# Function to trigger cold start
trigger_cold_start() {
    echo -e "${YELLOW}Triggering cold start by updating environment variable...${NC}"

    # Update a dummy environment variable to force new container
    TIMESTAMP=$(date +%s)
    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --environment "Variables={BENCHMARK_RUN=$TIMESTAMP}" \
        --output json > /dev/null

    echo "Waiting for function update to complete (30 seconds)..."
    sleep 30

    # Wait for function to be ready
    while true; do
        STATUS=$(aws lambda get-function --function-name "$FUNCTION_NAME" \
            --query 'Configuration.LastUpdateStatus' --output text)
        if [ "$STATUS" == "Successful" ]; then
            break
        fi
        echo "Function status: $STATUS, waiting..."
        sleep 5
    done

    echo "Waiting for old containers to shut down (60 seconds)..."
    sleep 60
}

# Function to invoke and measure
measure_invocation() {
    local test_type=$1
    local output_file="lambda-invoke-output-$$.json"
    local log_file="lambda-invoke-log-$$.log"

    # Create test payload
    local payload='{"body":"{\"prompt\":\"benchmark test\",\"steps\":25,\"guidance\":7,\"ip\":\"1.2.3.4\"}","httpMethod":"POST","path":"/generate","headers":{"Content-Type":"application/json"}}'

    # Invoke function and capture duration
    START_TIME=$(date +%s%N)
    aws lambda invoke \
        --function-name "$FUNCTION_NAME" \
        --payload "$payload" \
        --log-type Tail \
        --query 'LogResult' \
        --output text \
        "$output_file" 2>&1 | base64 -d > "$log_file" || true
    END_TIME=$(date +%s%N)

    # Calculate total invocation time (wall clock)
    WALL_CLOCK_MS=$(( ($END_TIME - $START_TIME) / 1000000 ))

    # Extract init duration and duration from logs
    if [ -f "$log_file" ]; then
        INIT_DURATION=$(grep "Init Duration:" "$log_file" | awk '{print $3}' | sed 's/ms//' || echo "0")
        BILLED_DURATION=$(grep "Billed Duration:" "$log_file" | awk '{print $3}' | sed 's/ms//' || echo "0")
        MEMORY_USED=$(grep "Memory Used:" "$log_file" | awk '{print $3}' | sed 's/MB//' || echo "0")
        MAX_MEMORY=$(grep "Max Memory Used:" "$log_file" | awk '{print $4}' | sed 's/MB//' || echo "0")
    else
        INIT_DURATION="0"
        BILLED_DURATION="0"
        MEMORY_USED="0"
        MAX_MEMORY="0"
    fi

    # Calculate total cold start time
    if [ "$INIT_DURATION" != "0" ]; then
        TOTAL_TIME=$(echo "$INIT_DURATION + $BILLED_DURATION" | bc)
    else
        TOTAL_TIME=$BILLED_DURATION
    fi

    # Output result
    echo "$test_type,$INIT_DURATION,$BILLED_DURATION,$TOTAL_TIME,$WALL_CLOCK_MS,$MEMORY_USED,$MAX_MEMORY"

    # Cleanup
    rm -f "$output_file" "$log_file"
}

# Main benchmarking
echo -e "${YELLOW}=== Cold Start Measurements ===${NC}"
echo "Running 5 cold start measurements..."
echo ""

COLD_RESULTS_FILE="cold-start-results-$$.csv"
echo "Type,InitDuration(ms),BilledDuration(ms),TotalTime(ms),WallClock(ms),MemoryUsed(MB),MaxMemory(MB)" > "$COLD_RESULTS_FILE"

for i in {1..5}; do
    echo -e "${YELLOW}Cold Start Test $i/5${NC}"
    trigger_cold_start
    RESULT=$(measure_invocation "cold")
    echo "$RESULT" >> "$COLD_RESULTS_FILE"
    echo "  Result: $RESULT"
    echo ""
done

echo -e "${YELLOW}=== Warm Start Measurements ===${NC}"
echo "Running 10 warm start measurements..."
echo ""

WARM_RESULTS_FILE="warm-start-results-$$.csv"
echo "Type,InitDuration(ms),BilledDuration(ms),TotalTime(ms),WallClock(ms),MemoryUsed(MB),MaxMemory(MB)" > "$WARM_RESULTS_FILE"

for i in {1..10}; do
    echo "Warm Start Test $i/10"
    RESULT=$(measure_invocation "warm")
    echo "$RESULT" >> "$WARM_RESULTS_FILE"
    echo "  Result: $RESULT"
    sleep 2  # Small delay between warm invocations
done

echo ""
echo -e "${GREEN}=== Benchmark Complete ===${NC}"
echo ""

# Calculate statistics
calculate_stats() {
    local file=$1
    local column=$2
    local label=$3

    # Extract column values (skip header)
    VALUES=$(tail -n +2 "$file" | cut -d',' -f"$column")

    # Calculate average, min, max
    AVG=$(echo "$VALUES" | awk '{sum+=$1} END {print sum/NR}')
    MIN=$(echo "$VALUES" | sort -n | head -1)
    MAX=$(echo "$VALUES" | sort -n | tail -1)

    # Calculate P95 (95th percentile)
    P95=$(echo "$VALUES" | sort -n | awk 'BEGIN {p=0.95} {a[NR]=$1} END {print a[int(NR*p)]}')

    printf "%-20s Avg: %8.2f ms  Min: %8.2f ms  Max: %8.2f ms  P95: %8.2f ms\n" \
        "$label" "$AVG" "$MIN" "$MAX" "$P95"
}

echo -e "${YELLOW}Cold Start Statistics:${NC}"
calculate_stats "$COLD_RESULTS_FILE" 2 "Init Duration:"
calculate_stats "$COLD_RESULTS_FILE" 3 "Billed Duration:"
calculate_stats "$COLD_RESULTS_FILE" 4 "Total Time:"
calculate_stats "$COLD_RESULTS_FILE" 5 "Wall Clock:"
echo ""

echo -e "${YELLOW}Warm Start Statistics:${NC}"
calculate_stats "$WARM_RESULTS_FILE" 3 "Billed Duration:"
calculate_stats "$WARM_RESULTS_FILE" 4 "Total Time:"
calculate_stats "$WARM_RESULTS_FILE" 5 "Wall Clock:"
echo ""

# Check against targets
COLD_AVG=$(tail -n +2 "$COLD_RESULTS_FILE" | cut -d',' -f4 | awk '{sum+=$1} END {print sum/NR}')
WARM_AVG=$(tail -n +2 "$WARM_RESULTS_FILE" | cut -d',' -f3 | awk '{sum+=$1} END {print sum/NR}')

echo -e "${YELLOW}Target Comparison:${NC}"
if (( $(echo "$COLD_AVG < 3000" | bc -l) )); then
    echo -e "  Cold Start: ${GREEN}✓ $COLD_AVG ms < 3000 ms target${NC}"
else
    echo -e "  Cold Start: ${RED}✗ $COLD_AVG ms > 3000 ms target${NC}"
fi

if (( $(echo "$WARM_AVG < 500" | bc -l) )); then
    echo -e "  Warm Start: ${GREEN}✓ $WARM_AVG ms < 500 ms target${NC}"
else
    echo -e "  Warm Start: ${YELLOW}⚠ $WARM_AVG ms > 500 ms target${NC}"
    echo -e "    ${YELLOW}Note: Warm time includes AI API calls, which can be slow${NC}"
fi

echo ""
echo -e "${YELLOW}Results saved to:${NC}"
echo "  Cold start data: $COLD_RESULTS_FILE"
echo "  Warm start data: $WARM_RESULTS_FILE"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Review results and add to docs/PERFORMANCE.md"
echo "2. If cold start > 3s, consider Lambda Layers or Reserved Concurrency"
echo "3. Archive results: mkdir -p benchmarks && mv *-results-*.csv benchmarks/"
echo ""
