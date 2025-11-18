#!/usr/bin/env bash
# Diagnostic script for prompt enhancement issues

set -e

echo "=== Prompt Enhancement Diagnostics ==="
echo ""

# Check if stack name is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <stack-name>"
    echo "Example: $0 pixel-prompt-prod"
    exit 1
fi

STACK_NAME="$1"

echo "Checking configuration for stack: $STACK_NAME"
echo ""

# Get stack parameters
echo "1. Checking MODEL_COUNT and PROMPT_MODEL_INDEX..."
MODEL_COUNT=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Parameters[?ParameterKey=='ModelCount'].ParameterValue" \
    --output text 2>/dev/null || echo "")

PROMPT_MODEL_INDEX=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Parameters[?ParameterKey=='PromptModelIndex'].ParameterValue" \
    --output text 2>/dev/null || echo "")

if [ -z "$MODEL_COUNT" ] || [ -z "$PROMPT_MODEL_INDEX" ]; then
    echo "❌ Could not retrieve stack parameters. Is the stack name correct?"
    exit 1
fi

echo "   MODEL_COUNT: $MODEL_COUNT"
echo "   PROMPT_MODEL_INDEX: $PROMPT_MODEL_INDEX"
echo ""

# Validate PROMPT_MODEL_INDEX is within range
if [ "$PROMPT_MODEL_INDEX" -lt 1 ] || [ "$PROMPT_MODEL_INDEX" -gt "$MODEL_COUNT" ]; then
    echo "❌ ERROR: PROMPT_MODEL_INDEX ($PROMPT_MODEL_INDEX) is out of range!"
    echo "   Valid range: 1 to $MODEL_COUNT"
    echo ""
    echo "Fix: Update the stack with a valid PromptModelIndex:"
    echo "  sam deploy --parameter-overrides PromptModelIndex=1"
    exit 1
fi

echo "✅ PROMPT_MODEL_INDEX is valid (within range 1-$MODEL_COUNT)"
echo ""

# Check the prompt model configuration
echo "2. Checking Model $PROMPT_MODEL_INDEX configuration..."

MODEL_PROVIDER=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Parameters[?ParameterKey=='Model${PROMPT_MODEL_INDEX}Provider'].ParameterValue" \
    --output text 2>/dev/null || echo "")

MODEL_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Parameters[?ParameterKey=='Model${PROMPT_MODEL_INDEX}Id'].ParameterValue" \
    --output text 2>/dev/null || echo "")

echo "   Model ${PROMPT_MODEL_INDEX} Provider: $MODEL_PROVIDER"
echo "   Model ${PROMPT_MODEL_INDEX} ID: $MODEL_ID"
echo ""

if [ -z "$MODEL_PROVIDER" ] || [ -z "$MODEL_ID" ]; then
    echo "❌ ERROR: Model $PROMPT_MODEL_INDEX is not configured!"
    echo ""
    echo "Fix: Configure the model with provider and ID:"
    echo "  sam deploy --parameter-overrides \\"
    echo "    Model${PROMPT_MODEL_INDEX}Provider=\"openai\" \\"
    echo "    Model${PROMPT_MODEL_INDEX}Id=\"gpt-4o-mini\" \\"
    echo "    Model${PROMPT_MODEL_INDEX}ApiKey=\"your-api-key\""
    exit 1
fi

# Check if provider is supported for prompt enhancement
SUPPORTED_PROVIDERS=("openai" "google_gemini" "generic")
PROVIDER_SUPPORTED=0

for provider in "${SUPPORTED_PROVIDERS[@]}"; do
    if [ "$MODEL_PROVIDER" = "$provider" ]; then
        PROVIDER_SUPPORTED=1
        break
    fi
done

if [ $PROVIDER_SUPPORTED -eq 0 ]; then
    echo "⚠️  WARNING: Provider '$MODEL_PROVIDER' may not support prompt enhancement"
    echo "   Supported providers: openai, google_gemini, generic (OpenAI-compatible)"
    echo ""
else
    echo "✅ Provider '$MODEL_PROVIDER' supports prompt enhancement"
    echo ""
fi

# Get recent CloudWatch logs
echo "3. Checking recent CloudWatch logs for enhancement errors..."
echo ""

FUNCTION_NAME=$(aws cloudformation describe-stack-resources \
    --stack-name "$STACK_NAME" \
    --query "StackResources[?ResourceType=='AWS::Lambda::Function'].PhysicalResourceId" \
    --output text 2>/dev/null || echo "")

if [ -z "$FUNCTION_NAME" ]; then
    echo "❌ Could not find Lambda function for stack"
    exit 1
fi

# Get logs from last 5 minutes
echo "   Searching logs for 'enhance' and 'prompt' keywords..."
echo ""

aws logs tail "/aws/lambda/$FUNCTION_NAME" \
    --since 5m \
    --filter-pattern "enhance" \
    --format short 2>/dev/null | head -20 || echo "   No recent enhancement logs found"

echo ""
echo "=== Diagnostics Complete ==="
echo ""
echo "Next steps:"
echo "1. If PROMPT_MODEL_INDEX is invalid, update it with: sam deploy --parameter-overrides PromptModelIndex=N"
echo "2. If model is not configured, configure it with provider, ID, and API key"
echo "3. Check CloudWatch logs for specific errors: sam logs --stack-name $STACK_NAME --tail"
echo "4. Test the endpoint with: ./scripts/test-enhance-endpoint.sh <api-endpoint>"
