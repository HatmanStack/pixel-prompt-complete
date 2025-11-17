# Deployment Guide - Pixel Prompt Complete Backend

Complete guide for deploying the Pixel Prompt Complete serverless backend to AWS.

## Prerequisites

### Required Tools

- **AWS CLI**: v2+ configured with credentials
  ```bash
  aws --version
  aws configure
  ```

- **AWS SAM CLI**: Latest version (1.100+)
  ```bash
  sam --version
  # Install: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
  ```

- **Python**: 3.12+
  ```bash
  python --version
  ```

### AWS Account Requirements

Your AWS account must have:

- **IAM Permissions**: Create roles, policies, Lambda functions
- **Service Access**: Lambda, S3, CloudFront, API Gateway
- **AWS Bedrock Access**: Enabled for Nova Canvas (us-east-1) and Stable Diffusion (us-west-2)
- **Sufficient Quotas**: Lambda concurrent executions, S3 storage

### API Keys

Prepare API keys for the AI models you want to use:

- **OpenAI**: For DALL-E 3 - [Get key](https://platform.openai.com/api-keys)
- **Google Cloud**: For Gemini 2.0 and Imagen 3.0 - [Get key](https://ai.google.dev/)
- **Stability AI**: For Stable Diffusion - [Get key](https://platform.stability.ai/)
- **Black Forest Labs**: For Flux models - [Get key](https://api.bfl.ai/)
- **Recraft**: For Recraft v3 - [Get key](https://www.recraft.ai/)
- **AWS Credentials**: For Bedrock models (use AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)

## Configuration

### Step 1: Configure Parameters

1. Copy the example parameters file:
   ```bash
   cd backend
   cp parameters.example.json parameters.json
   ```

2. Edit `parameters.json` with your API keys:
   ```json
   {
     "Parameters": {
       "ModelCount": 9,
       "Model1Name": "DALL-E 3",
       "Model1Key": "sk-your-actual-key-here",
       ...
     }
   }
   ```

   **Notes**:
   - `ModelCount`: Set to the number of models you want (1-20)
   - `ModelXName`: Name of the AI model (used for provider detection)
   - `ModelXKey`: API key for that model
   - Use `"N/A"` for Bedrock models (they use AWS credentials)
   - `PromptModelIndex`: Which model to use for prompt enhancement (1-based)
   - Leave unused model slots empty (`""`)

3. Add `parameters.json` to `.gitignore` (already configured):
   ```bash
   # Verify it's ignored
   git status | grep parameters.json
   # Should not appear
   ```

### Step 2: Set AWS Credentials for Bedrock

If using AWS Bedrock models (Nova Canvas, Stable Diffusion):

```bash
export AWS_ACCESS_KEY_ID="your-aws-access-key"
export AWS_SECRET_ACCESS_KEY="your-aws-secret-key"
```

Or configure in your SAM deployment parameters.

## Deployment Steps

### First Deployment (Interactive)

1. **Build** the SAM application:
   ```bash
   cd backend
   sam build
   ```

   This will:
   - Install Python dependencies from `requirements.txt`
   - Package Lambda code
   - Prepare CloudFormation template

2. **Deploy** with guided workflow:
   ```bash
   sam deploy --guided
   ```

   You'll be prompted for:
   - **Stack Name**: `pixel-prompt-complete-dev` (or your choice)
   - **AWS Region**: `us-west-2` (or your preferred region)
   - **ModelCount**: `9` (or your desired number)
   - **Model1Name through Model9Name**: Names of your models
   - **Model1Key through Model9Key**: Your API keys (won't echo to screen)
   - **PromptModelIndex**: `1` (or which model to use for enhancement)
   - **GlobalRateLimit**: `1000` (requests per hour)
   - **IPRateLimit**: `50` (requests per day per IP)
   - **IPWhitelist**: `` (comma-separated IPs to bypass limits)
   - **Confirm changes before deploy**: `Y`
   - **Allow SAM CLI IAM role creation**: `Y`
   - **Disable rollback**: `N`
   - **Save arguments to configuration file**: `Y`
   - **SAM configuration file**: `samconfig.toml` (default)
   - **SAM configuration environment**: `default` (default)

3. **Wait** for deployment (10-20 minutes for CloudFront):
   - Lambda, S3, API Gateway: ~2-5 minutes
   - CloudFront distribution: ~10-15 minutes (one-time)

4. **Get outputs**:
   ```bash
   sam list stack-outputs --stack-name pixel-prompt-complete-dev
   ```

   Save these values:
   - `ApiEndpoint`: Use this in your frontend
   - `CloudFrontDomain`: Used for serving images
   - `S3BucketName`: Where images are stored

### Subsequent Deployments

After the first deployment, you can use the saved configuration:

```bash
# Build and deploy
sam build && sam deploy

# Or deploy only (if no code changes)
sam deploy
```

### Deploy with Parameter File

If you created `parameters.json`:

```bash
sam build

# Extract parameters and deploy
sam deploy --parameter-overrides $(cat parameters.json | jq -r '.Parameters | to_entries | map("\(.key)=\(.value)") | join(" ")')
```

Or use a shell script:

```bash
#!/bin/bash
# deploy.sh

sam build

# Read parameters from JSON
PARAMS=$(cat parameters.json | jq -r '.Parameters | to_entries | map("\(.key)=\(.value)") | join(" ")')

# Deploy with parameters
sam deploy --parameter-overrides $PARAMS
```

## Verification

### 1. Check Stack Status

```bash
aws cloudformation describe-stacks --stack-name pixel-prompt-complete-dev
```

Status should be `CREATE_COMPLETE` or `UPDATE_COMPLETE`.

### 2. Test API Endpoints

Get the API endpoint from outputs:

```bash
API_ENDPOINT=$(sam list stack-outputs --stack-name pixel-prompt-complete-dev | grep ApiEndpoint | awk '{print $2}')
echo "API Endpoint: $API_ENDPOINT"
```

Test each endpoint:

```bash
# Test POST /generate
curl -X POST $API_ENDPOINT/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"beautiful sunset","steps":25,"guidance":7,"ip":"1.2.3.4"}'

# Should return:
# {"message":"Generate endpoint (placeholder)",...}

# Test GET /status/{jobId}
curl $API_ENDPOINT/status/test-job-id

# Should return:
# {"jobId":"test-job-id","status":"pending",...}

# Test POST /enhance
curl -X POST $API_ENDPOINT/enhance \
  -H "Content-Type: application/json" \
  -d '{"prompt":"cat"}'

# Should return:
# {"enhanced":"Enhanced version of: cat",...}
```

### 3. Check Lambda Function

```bash
# View function details
aws lambda get-function --function-name pixel-prompt-complete-dev-function

# View logs (real-time)
sam logs --stack-name pixel-prompt-complete-dev --tail

# View recent logs
sam logs --stack-name pixel-prompt-complete-dev --start-time '10min ago'
```

### 4. Verify S3 Bucket

```bash
S3_BUCKET=$(sam list stack-outputs --stack-name pixel-prompt-complete-dev | grep S3BucketName | awk '{print $2}')

# List bucket
aws s3 ls s3://$S3_BUCKET

# Test upload
echo "test" > test.txt
aws s3 cp test.txt s3://$S3_BUCKET/test.txt
rm test.txt
```

### 5. Verify CloudFront

```bash
CLOUDFRONT_DOMAIN=$(sam list stack-outputs --stack-name pixel-prompt-complete-dev | grep CloudFrontDomain | awk '{print $2}')

# Test CloudFront access
curl https://$CLOUDFRONT_DOMAIN/test.txt

# Should return: "test"
```

## Updating the Deployment

### Update Lambda Code Only

After changing Python code in `src/`:

```bash
sam build && sam deploy
```

### Update Model Configuration

To change model names or API keys:

```bash
sam deploy --parameter-overrides ModelCount=10 Model1Key=new-key-here
```

Or update `parameters.json` and redeploy:

```bash
# Edit parameters.json
vim parameters.json

# Deploy
sam build
sam deploy --parameter-overrides $(cat parameters.json | jq -r '.Parameters | to_entries | map("\(.key)=\(.value)") | join(" ")')
```

### Update Infrastructure

After changing `template.yaml`:

```bash
sam build
sam deploy
```

SAM will show you a changeset before applying updates.

## Multiple Environments

Deploy separate stacks for dev/staging/prod:

```bash
# Development
sam deploy --stack-name pixel-prompt-complete-dev --parameter-overrides Environment=dev

# Staging
sam deploy --stack-name pixel-prompt-complete-staging --parameter-overrides Environment=staging

# Production
sam deploy --stack-name pixel-prompt-complete-prod --parameter-overrides Environment=prod
```

Each stack gets its own:
- Lambda function
- S3 bucket
- CloudFront distribution
- API Gateway endpoint

## Monitoring and Debugging

### CloudWatch Logs

View logs in real-time:

```bash
sam logs --stack-name pixel-prompt-complete-dev --tail
```

View specific log streams:

```bash
aws logs tail /aws/lambda/pixel-prompt-complete-dev-function --follow
```

### CloudWatch Alarms

The stack creates alarms for:
- Lambda errors (> 5 in 5 minutes)
- Lambda duration (average > 2 minutes)

View alarms:

```bash
aws cloudwatch describe-alarms --alarm-name-prefix pixel-prompt-complete-dev
```

### Lambda Metrics

View Lambda metrics in CloudWatch:
- Invocations
- Errors
- Duration
- Throttles
- Concurrent executions

Or via CLI:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=pixel-prompt-complete-dev-function \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

## Cost Management

### Cost Estimation

For moderate usage (~1000 generations/month with 9 models):

- **Lambda**: ~$15-30/month
  - 1000 invocations × 60s average × 3008MB = ~$15
- **S3**: ~$1-5/month
  - Storage + requests
- **CloudFront**: ~$1-10/month
  - Data transfer
- **API Gateway**: ~$0.01/month
  - HTTP API is very cheap

**Total: $20-50/month** depending on usage

### Cost Optimization

1. **Reduce Lambda memory** if parallel execution isn't needed:
   ```yaml
   MemorySize: 1024  # Instead of 3008
   ```

2. **Enable S3 lifecycle policies** (already configured):
   - Images deleted after 30 days

3. **Use Lambda reserved concurrency** (already configured):
   - Prevents runaway costs: `ReservedConcurrentExecutions: 10`

4. **Monitor costs**:
   ```bash
   aws ce get-cost-and-usage \
     --time-period Start=2025-11-01,End=2025-11-30 \
     --granularity MONTHLY \
     --metrics BlendedCost \
     --group-by Type=SERVICE
   ```

## Cleanup

### Delete Stack

To delete all resources:

```bash
sam delete --stack-name pixel-prompt-complete-dev
```

This removes:
- Lambda function
- API Gateway
- CloudFront distribution
- S3 bucket policy

**Note**: S3 bucket is **retained** by default (DeletionPolicy: Retain) to prevent accidental data loss.

### Delete S3 Bucket

If you want to delete the S3 bucket and all images:

```bash
# List bucket contents
aws s3 ls s3://pixel-prompt-complete-<account-id>

# Delete all objects
aws s3 rm s3://pixel-prompt-complete-<account-id> --recursive

# Delete bucket
aws s3 rb s3://pixel-prompt-complete-<account-id>
```

## Troubleshooting

### Deployment Fails

**Problem**: CloudFormation stack fails to create

**Solutions**:
- Check CloudFormation events:
  ```bash
  aws cloudformation describe-stack-events --stack-name pixel-prompt-complete-dev --max-items 20
  ```
- Check IAM permissions (need Lambda, S3, CloudFront, API Gateway permissions)
- Verify bucket name is unique (uses account ID)

### API Returns 500 Errors

**Problem**: API calls return 500 Internal Server Error

**Solutions**:
- Check Lambda logs:
  ```bash
  sam logs --stack-name pixel-prompt-complete-dev --tail
  ```
- Verify environment variables are set correctly
- Check Python dependencies installed: `sam build` output
- Test Lambda locally:
  ```bash
  sam local invoke -e events/generate.json
  ```

### API Returns 403 Forbidden

**Problem**: API calls return 403 Forbidden

**Solutions**:
- Verify API Gateway is deployed
- Check CORS configuration in template
- Verify request includes required headers

### Images Not Accessible

**Problem**: Cannot access images via CloudFront URL

**Solutions**:
- Wait 10-15 minutes for CloudFront distribution to deploy
- Verify S3 bucket policy allows CloudFront OAI access
- Check CloudFront distribution status:
  ```bash
  aws cloudfront get-distribution --id <distribution-id>
  ```

### Rate Limiting Issues

**Problem**: Getting rate limited too quickly

**Solutions**:
- Increase rate limits in parameters:
  ```bash
  sam deploy --parameter-overrides GlobalRateLimit=5000 IPRateLimit=200
  ```
- Add your IP to whitelist:
  ```bash
  sam deploy --parameter-overrides IPWhitelist=1.2.3.4,5.6.7.8
  ```

### AWS Bedrock Model Not Available

**Problem**: Bedrock models return errors

**Solutions**:
- Verify Bedrock access is enabled in correct region:
  - Nova Canvas: `us-east-1`
  - Stable Diffusion: `us-west-2`
- Check AWS credentials are configured
- Verify model access in AWS Console → Bedrock → Model access

## Advanced Configuration

### Custom Domain

To use a custom domain (e.g., `api.yourdomain.com`):

1. Register domain in Route 53
2. Create ACM certificate
3. Add custom domain to API Gateway
4. Update DNS records

See: [API Gateway Custom Domains](https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-custom-domains.html)

### VPC Configuration

To deploy Lambda in VPC (for enhanced security):

1. Update `template.yaml`:
   ```yaml
   PixelPromptFunction:
     Properties:
       VpcConfig:
         SecurityGroupIds:
           - sg-xxxxx
         SubnetIds:
           - subnet-xxxxx
           - subnet-yyyyy
   ```

2. Add NAT Gateway for internet access (Bedrock, external APIs)

### Environment Variables

To add custom environment variables:

1. Edit `template.yaml`:
   ```yaml
   Environment:
     Variables:
       CUSTOM_VAR: value
   ```

2. Redeploy:
   ```bash
   sam build && sam deploy
   ```

## Support

- **AWS SAM Documentation**: https://docs.aws.amazon.com/serverless-application-model/
- **Implementation Plans**: See `../docs/plans/`
- **GitHub Issues**: (link to your repo)

## Next Steps

After successful deployment:

1. Save the API endpoint URL
2. Test all three endpoints (generate, status, enhance)
3. Proceed to Phase 2: Frontend Implementation
4. Configure frontend to use the API endpoint

Ready to build the web interface!
