#!/usr/bin/env bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default environment
ENVIRONMENT="${1:-dev}"

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    echo -e "${RED}Error: Invalid environment '$ENVIRONMENT'${NC}"
    echo "Usage: $0 [dev|staging|prod]"
    exit 1
fi

echo -e "${GREEN}=== Pixel Prompt Backend Deployment ===${NC}"
echo -e "Environment: ${YELLOW}$ENVIRONMENT${NC}"
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI not found. Please install: https://aws.amazon.com/cli/${NC}"
    exit 1
fi

# Check SAM CLI
if ! command -v sam &> /dev/null; then
    echo -e "${RED}Error: SAM CLI not found. Please install: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html${NC}"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}Error: AWS credentials not configured. Run 'aws configure'${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Prerequisites OK${NC}"
echo ""

# Navigate to backend directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/../backend"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"

cd "$BACKEND_DIR"

# Configuration file
ENV_DEPLOY_FILE="$BACKEND_DIR/.env.deploy"

# Load existing configuration if present
if [ -f "$ENV_DEPLOY_FILE" ]; then
    set -a
    source "$ENV_DEPLOY_FILE"
    set +a
fi

# Set defaults
DEFAULT_REGION="${AWS_REGION:-us-west-2}"
DEFAULT_STACK="${STACK_NAME:-pixel-prompt-$ENVIRONMENT}"
DEFAULT_MODEL_COUNT="${MODEL_COUNT:-1}"

# Check if we need configuration
NEED_CONFIG=false
if [ -z "$MODEL_1_PROVIDER" ] || [ -z "$MODEL_1_ID" ]; then
    NEED_CONFIG=true
fi
if [ -z "$PROMPT_MODEL_PROVIDER" ] || [ -z "$PROMPT_MODEL_ID" ]; then
    NEED_CONFIG=true
fi

# Interactive configuration
if [ "$NEED_CONFIG" = true ]; then
    echo -e "${CYAN}Configuration required. Please provide the following:${NC}"
    echo ""

    # Basic settings
    read -p "AWS Region [$DEFAULT_REGION]: " AWS_REGION
    AWS_REGION=${AWS_REGION:-$DEFAULT_REGION}

    read -p "Stack name [$DEFAULT_STACK]: " STACK_NAME
    STACK_NAME=${STACK_NAME:-$DEFAULT_STACK}

    echo ""
    echo -e "${CYAN}=== Prompt Enhancement Model ===${NC}"
    echo "This model is used to enhance/improve user prompts before image generation."
    echo "Recommended: OpenAI GPT-4o or Google Gemini"
    echo ""

    if [ -n "$PROMPT_MODEL_PROVIDER" ]; then
        read -p "Provider (openai/google_gemini) [${PROMPT_MODEL_PROVIDER}]: " NEW_PROMPT_PROVIDER
        PROMPT_MODEL_PROVIDER=${NEW_PROMPT_PROVIDER:-$PROMPT_MODEL_PROVIDER}
    else
        read -p "Provider (openai/google_gemini): " PROMPT_MODEL_PROVIDER
    fi

    if [ -n "$PROMPT_MODEL_ID" ]; then
        read -p "Model ID [${PROMPT_MODEL_ID}]: " NEW_PROMPT_ID
        PROMPT_MODEL_ID=${NEW_PROMPT_ID:-$PROMPT_MODEL_ID}
    else
        if [ "$PROMPT_MODEL_PROVIDER" = "openai" ]; then
            read -p "Model ID [gpt-4o]: " PROMPT_MODEL_ID
            PROMPT_MODEL_ID=${PROMPT_MODEL_ID:-gpt-4o}
        else
            read -p "Model ID: " PROMPT_MODEL_ID
        fi
    fi

    if [ -n "$PROMPT_MODEL_API_KEY" ]; then
        read -p "API Key [****${PROMPT_MODEL_API_KEY: -4}]: " NEW_PROMPT_KEY
        PROMPT_MODEL_API_KEY=${NEW_PROMPT_KEY:-$PROMPT_MODEL_API_KEY}
    else
        read -p "API Key: " PROMPT_MODEL_API_KEY
    fi

    echo ""
    echo -e "${CYAN}=== Image Generation Models ===${NC}"
    echo "Configure the AI models that will generate images."
    echo "Supported providers: openai, google_gemini, bedrock_nova, bedrock_sd, bfl, recraft, stability"
    echo ""

    read -p "How many image generation models? [$DEFAULT_MODEL_COUNT]: " MODEL_COUNT
    MODEL_COUNT=${MODEL_COUNT:-$DEFAULT_MODEL_COUNT}

    for i in $(seq 1 $MODEL_COUNT); do
        echo ""
        echo -e "${YELLOW}--- Model $i ---${NC}"

        PROVIDER_VAR="MODEL_${i}_PROVIDER"
        ID_VAR="MODEL_${i}_ID"
        API_KEY_VAR="MODEL_${i}_API_KEY"

        EXISTING_PROVIDER="${!PROVIDER_VAR}"
        EXISTING_ID="${!ID_VAR}"
        EXISTING_KEY="${!API_KEY_VAR}"

        if [ -n "$EXISTING_PROVIDER" ]; then
            read -p "Provider [$EXISTING_PROVIDER]: " NEW_PROVIDER
            eval "MODEL_${i}_PROVIDER=\${NEW_PROVIDER:-$EXISTING_PROVIDER}"
        else
            read -p "Provider: " "MODEL_${i}_PROVIDER"
        fi

        CURRENT_PROVIDER="${!PROVIDER_VAR}"

        if [ -n "$EXISTING_ID" ]; then
            read -p "Model ID [$EXISTING_ID]: " NEW_ID
            eval "MODEL_${i}_ID=\${NEW_ID:-$EXISTING_ID}"
        else
            # Suggest default model IDs based on provider
            case "$CURRENT_PROVIDER" in
                openai) DEFAULT_ID="gpt-image-1" ;;
                google_gemini) DEFAULT_ID="gemini-2.0-flash-preview-image-generation" ;;
                bedrock_nova) DEFAULT_ID="amazon.nova-canvas-v1:0" ;;
                bedrock_sd) DEFAULT_ID="stability.sd3-5-large-v1:0" ;;
                bfl) DEFAULT_ID="flux-pro-1.1" ;;
                recraft) DEFAULT_ID="recraft-v3" ;;
                *) DEFAULT_ID="" ;;
            esac
            if [ -n "$DEFAULT_ID" ]; then
                read -p "Model ID [$DEFAULT_ID]: " "MODEL_${i}_ID"
                eval "MODEL_${i}_ID=\${MODEL_${i}_ID:-$DEFAULT_ID}"
            else
                read -p "Model ID: " "MODEL_${i}_ID"
            fi
        fi

        # API key (not needed for Bedrock)
        if [[ "$CURRENT_PROVIDER" != bedrock_* ]]; then
            if [ -n "$EXISTING_KEY" ]; then
                read -p "API Key [****${EXISTING_KEY: -4}]: " NEW_KEY
                eval "MODEL_${i}_API_KEY=\${NEW_KEY:-$EXISTING_KEY}"
            else
                read -p "API Key: " "MODEL_${i}_API_KEY"
            fi
        else
            echo "  (Bedrock uses IAM role - no API key needed)"
            eval "MODEL_${i}_API_KEY="
        fi
    done

    echo ""
    echo -e "${YELLOW}Saving configuration to .env.deploy...${NC}"

    # Write configuration file
    cat > "$ENV_DEPLOY_FILE" << EOF
# Pixel Prompt Deployment Configuration
# Auto-generated on $(date)

# AWS Configuration
AWS_REGION=$AWS_REGION
STACK_NAME=$STACK_NAME

# Lambda Configuration
LAMBDA_MEMORY=${LAMBDA_MEMORY:-3008}
LAMBDA_TIMEOUT=${LAMBDA_TIMEOUT:-900}

# Rate Limiting
GLOBAL_RATE_LIMIT=${GLOBAL_RATE_LIMIT:-1000}
IP_RATE_LIMIT=${IP_RATE_LIMIT:-100}

# S3 Configuration
S3_RETENTION_DAYS=${S3_RETENTION_DAYS:-30}

# Prompt Enhancement Model (for /enhance endpoint)
PROMPT_MODEL_PROVIDER=$PROMPT_MODEL_PROVIDER
PROMPT_MODEL_ID=$PROMPT_MODEL_ID
PROMPT_MODEL_API_KEY=$PROMPT_MODEL_API_KEY

# Image Generation Models
MODEL_COUNT=$MODEL_COUNT
EOF

    for i in $(seq 1 $MODEL_COUNT); do
        PROVIDER_VAR="MODEL_${i}_PROVIDER"
        ID_VAR="MODEL_${i}_ID"
        API_KEY_VAR="MODEL_${i}_API_KEY"

        cat >> "$ENV_DEPLOY_FILE" << EOF

# Model $i
MODEL_${i}_PROVIDER=${!PROVIDER_VAR}
MODEL_${i}_ID=${!ID_VAR}
MODEL_${i}_API_KEY=${!API_KEY_VAR}
EOF
    done

    echo -e "${GREEN}✓ Configuration saved${NC}"
    echo ""
else
    echo -e "${GREEN}✓ Configuration loaded from .env.deploy${NC}"
fi

# Display configuration summary
echo -e "${CYAN}=== Configuration Summary ===${NC}"
echo -e "Region:       ${YELLOW}$AWS_REGION${NC}"
echo -e "Stack:        ${YELLOW}$STACK_NAME${NC}"
echo ""
echo -e "Prompt Model: ${YELLOW}$PROMPT_MODEL_PROVIDER${NC} / ${YELLOW}$PROMPT_MODEL_ID${NC}"
echo ""
echo -e "Image Models: ${YELLOW}$MODEL_COUNT${NC}"
for i in $(seq 1 $MODEL_COUNT); do
    PROVIDER_VAR="MODEL_${i}_PROVIDER"
    ID_VAR="MODEL_${i}_ID"
    echo -e "  $i: ${YELLOW}${!PROVIDER_VAR}${NC} / ${YELLOW}${!ID_VAR}${NC}"
done
echo ""

# Build parameter overrides string
PARAM_OVERRIDES="Environment=$ENVIRONMENT"
PARAM_OVERRIDES+=" LambdaMemory=${LAMBDA_MEMORY:-3008}"
PARAM_OVERRIDES+=" LambdaTimeout=${LAMBDA_TIMEOUT:-900}"
PARAM_OVERRIDES+=" ModelCount=$MODEL_COUNT"
PARAM_OVERRIDES+=" GlobalRateLimit=${GLOBAL_RATE_LIMIT:-1000}"
PARAM_OVERRIDES+=" IPRateLimit=${IP_RATE_LIMIT:-100}"
PARAM_OVERRIDES+=" S3RetentionDays=${S3_RETENTION_DAYS:-30}"

# Add prompt enhancement model configuration
PARAM_OVERRIDES+=" PromptModelProvider=$PROMPT_MODEL_PROVIDER"
PARAM_OVERRIDES+=" PromptModelId=$PROMPT_MODEL_ID"
if [ -n "$PROMPT_MODEL_API_KEY" ]; then
    PARAM_OVERRIDES+=" PromptModelApiKey=$PROMPT_MODEL_API_KEY"
fi

# Add image generation model parameters
for i in $(seq 1 $MODEL_COUNT); do
    PROVIDER_VAR="MODEL_${i}_PROVIDER"
    ID_VAR="MODEL_${i}_ID"
    API_KEY_VAR="MODEL_${i}_API_KEY"

    PROVIDER="${!PROVIDER_VAR}"
    ID="${!ID_VAR}"
    API_KEY="${!API_KEY_VAR}"

    if [ -z "$PROVIDER" ] || [ -z "$ID" ]; then
        echo -e "${RED}Error: Model $i requires PROVIDER and ID${NC}"
        exit 1
    fi

    PARAM_OVERRIDES+=" Model${i}Provider=$PROVIDER"
    PARAM_OVERRIDES+=" Model${i}Id=$ID"

    if [ -n "$API_KEY" ]; then
        PARAM_OVERRIDES+=" Model${i}ApiKey=$API_KEY"
    fi
done

# Build
echo -e "${YELLOW}Building SAM application...${NC}"
if ! sam build; then
    echo -e "${RED}Error: SAM build failed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Build successful${NC}"
echo ""

# Deploy
echo -e "${YELLOW}Deploying to AWS...${NC}"
echo "This may take several minutes..."
echo ""

if ! sam deploy \
    --stack-name "$STACK_NAME" \
    --region "$AWS_REGION" \
    --capabilities CAPABILITY_IAM \
    --resolve-s3 \
    --parameter-overrides "$PARAM_OVERRIDES"; then
    echo -e "${RED}Error: SAM deploy failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Deployment successful${NC}"
echo ""

# Extract CloudFormation outputs
echo -e "${YELLOW}Extracting CloudFormation outputs...${NC}"

# Check if jq is available for better JSON parsing
if command -v jq &> /dev/null; then
    API_ENDPOINT=$(sam list stack-outputs --stack-name "$STACK_NAME" --output json 2>/dev/null | \
        jq -r '.[] | select(.OutputKey=="ApiEndpoint") | .OutputValue')
    S3_BUCKET=$(sam list stack-outputs --stack-name "$STACK_NAME" --output json 2>/dev/null | \
        jq -r '.[] | select(.OutputKey=="S3BucketName") | .OutputValue')
    CLOUDFRONT_DOMAIN=$(sam list stack-outputs --stack-name "$STACK_NAME" --output json 2>/dev/null | \
        jq -r '.[] | select(.OutputKey=="CloudFrontDomain") | .OutputValue')
else
    echo -e "${YELLOW}Note: jq not found, using awk (install jq for better reliability)${NC}"
    API_ENDPOINT=$(sam list stack-outputs --stack-name "$STACK_NAME" 2>/dev/null | \
        grep "ApiEndpoint" | awk '{print $2}')
    S3_BUCKET=$(sam list stack-outputs --stack-name "$STACK_NAME" 2>/dev/null | \
        grep "S3BucketName" | awk '{print $2}')
    CLOUDFRONT_DOMAIN=$(sam list stack-outputs --stack-name "$STACK_NAME" 2>/dev/null | \
        grep "CloudFrontDomain" | awk '{print $2}')
fi

if [ -z "$API_ENDPOINT" ]; then
    echo -e "${RED}Error: Could not extract API endpoint from CloudFormation outputs${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Outputs extracted${NC}"
echo ""

# Generate frontend .env file
echo -e "${YELLOW}Generating frontend .env file...${NC}"

ENV_FILE="$FRONTEND_DIR/.env"

cat > "$ENV_FILE" << EOF
# Auto-generated by deploy.sh on $(date)
# Environment: $ENVIRONMENT
# Stack: $STACK_NAME

VITE_API_ENDPOINT=$API_ENDPOINT
VITE_CLOUDFRONT_DOMAIN=$CLOUDFRONT_DOMAIN
VITE_S3_BUCKET=$S3_BUCKET
VITE_ENVIRONMENT=$ENVIRONMENT
EOF

echo -e "${GREEN}✓ Frontend .env file created at: $ENV_FILE${NC}"
echo ""

# Verify API endpoint
echo -e "${YELLOW}Verifying API endpoint...${NC}"
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_ENDPOINT/gallery/list" 2>/dev/null || echo "000")

if [ "$HTTP_STATUS" = "200" ]; then
    echo -e "${GREEN}✓ API endpoint is responding (HTTP 200)${NC}"
elif [ "$HTTP_STATUS" = "404" ]; then
    echo -e "${GREEN}✓ API endpoint is accessible (HTTP 404 - no galleries yet)${NC}"
else
    echo -e "${YELLOW}⚠ API endpoint returned HTTP $HTTP_STATUS${NC}"
    echo -e "${YELLOW}  CloudFront may still be deploying (~15 min)${NC}"
fi
echo ""

# Summary
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
echo -e "Stack Name:        ${YELLOW}$STACK_NAME${NC}"
echo -e "API Endpoint:      ${YELLOW}$API_ENDPOINT${NC}"
echo -e "CloudFront Domain: ${YELLOW}$CLOUDFRONT_DOMAIN${NC}"
echo -e "S3 Bucket:         ${YELLOW}$S3_BUCKET${NC}"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo "1. cd frontend && npm run build"
echo "2. cd frontend && npm run preview"
echo ""
