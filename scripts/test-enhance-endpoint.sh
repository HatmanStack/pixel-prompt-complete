#!/usr/bin/env bash
# Test script for prompt enhancement endpoint

set -e

# Check if API endpoint is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <api-endpoint>"
    echo "Example: $0 https://xyz.execute-api.us-east-1.amazonaws.com/Prod"
    exit 1
fi

API_ENDPOINT="$1"

echo "Testing prompt enhancement endpoint..."
echo "API Endpoint: $API_ENDPOINT"
echo ""

# Test with a simple prompt
echo "Testing with simple prompt: 'a cat'"
echo ""

RESPONSE=$(curl -s -X POST "$API_ENDPOINT/enhance" \
    -H "Content-Type: application/json" \
    -d '{"prompt":"a cat"}')

echo "Response:"
echo "$RESPONSE" | python3 -m json.tool

echo ""
echo "---"
echo ""

# Check if enhanced prompt differs from original
ORIGINAL=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('original', ''))")
SHORT=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('short_prompt', ''))")

if [ "$ORIGINAL" = "$SHORT" ]; then
    echo "⚠️  WARNING: Enhanced prompt is identical to original!"
    echo "This means enhancement is not working."
    echo ""
    echo "Common causes:"
    echo "1. PROMPT_MODEL_INDEX doesn't match any configured model"
    echo "2. The prompt model has no API key configured"
    echo "3. The prompt model provider is not supported for enhancement"
    echo ""
    echo "Check CloudWatch logs for details:"
    echo "  sam logs --stack-name <your-stack-name> --tail"
else
    echo "✅ Enhancement working - prompt was enhanced!"
fi
