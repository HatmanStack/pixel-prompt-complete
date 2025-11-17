# Production Deployment Guide

This guide covers deploying Pixel Prompt to production using GitHub Actions.

## Prerequisites

Before deploying to production:

1. **GitHub Secrets configured** - See [DEPLOYMENT_SECRETS.md](DEPLOYMENT_SECRETS.md)
2. **Staging deployment successful** - Test in staging first
3. **All tests passing** - CI must be green
4. **Security scans passing** - No high/critical vulnerabilities
5. **Production environment configured** - See setup below

## Setting Up Production Environment

### 1. Create Production Environment in GitHub

1. Go to **Settings** > **Environments** > **New environment**
2. Name: `production`
3. Configure protection rules:
   - ✅ **Required reviewers**: Add maintainers who can approve deployments
   - ✅ **Wait timer**: Optional (e.g., 5 minutes for review)
   - ⚠️ **Deployment branches**: Limit to `main` branch only
4. Click **Save protection rules**

### 2. Configure Production Secrets (Optional)

If using separate credentials for production:

1. Go to **Settings** > **Environments** > **production** > **Add secret**
2. Add production-specific secrets:
   - `AWS_ACCESS_KEY_ID` (production account)
   - `AWS_SECRET_ACCESS_KEY` (production account)
   - `MODEL_1_KEY` through `MODEL_9_KEY` (production API keys)
   - `STACK_NAME_PRODUCTION` (e.g., `pixel-prompt-prod`)

If not using environment-specific secrets, the workflow will use repository secrets.

## Deployment Methods

### Method 1: Manual Deployment (Recommended)

Manually trigger deployment with approval gate:

1. **Navigate to Actions**:
   - Go to repository > **Actions** tab
   - Select **Deploy to Production** workflow

2. **Trigger Deployment**:
   - Click **Run workflow** dropdown
   - Select branch: `main`
   - Enter confirmation: `deploy-production` (exact match required)
   - Click **Run workflow**

3. **Approve Deployment**:
   - Workflow will pause at `deploy-production` job
   - Required reviewer receives notification
   - Reviewer clicks **Review deployments** > **Approve and deploy**

4. **Monitor Deployment**:
   - Watch workflow progress in Actions tab
   - Check job logs for any errors
   - Verify deployment summary when complete

5. **Post-Deployment Verification**:
   - Test API endpoint manually
   - Check CloudWatch logs for errors
   - Verify all features working

### Method 2: Release Tag Deployment

Automatically deploy when creating a GitHub release:

1. **Create a Release**:
   - Go to **Releases** > **Draft a new release**
   - Tag version: `v1.0.0` (semantic versioning)
   - Target: `main` branch
   - Release title: `v1.0.0 - Description`
   - Description: Changelog and release notes
   - Click **Publish release**

2. **Approval and Deployment**:
   - Workflow triggers automatically
   - Required reviewer approves deployment
   - Deployment proceeds

3. **Release Notes**:
   - Workflow comments on release with deployment details
   - API endpoint and CloudFront URL included

## Deployment Workflow Steps

The production deployment workflow performs:

1. **Pre-Deployment Checks**:
   - Validates confirmation input
   - Checks version tag format (for releases)
   - Verifies tests passed

2. **Deployment**:
   - Waits for manual approval (environment protection)
   - Deploys CloudFormation stack with SAM
   - Configures Lambda, API Gateway, S3, CloudFront

3. **Health Checks**:
   - Tests `/gallery/list` endpoint
   - Tests `/generate` endpoint
   - Tests `/enhance` endpoint
   - Monitors CloudWatch logs for errors

4. **Reporting**:
   - Generates deployment summary
   - Posts comment on release (if applicable)
   - Creates issue on failure

## Monitoring Production

After deployment, monitor:

1. **CloudWatch Logs**:
   ```bash
   aws logs tail /aws/lambda/pixel-prompt-production-GenerateFunction --follow
   ```

2. **CloudWatch Metrics**:
   - Lambda invocations, errors, duration
   - API Gateway 4XX/5XX errors
   - S3 bucket size and requests

3. **Cost Monitoring**:
   - AWS Cost Explorer > Filter by tags
   - Set up budget alerts in AWS Billing

## Rollback Procedure

If deployment fails or introduces issues:

### Option 1: Revert and Redeploy

```bash
# Revert the problematic commits
git revert <commit-sha>

# Push to main
git push origin main

# Re-run staging deployment
# After verification, manually trigger production deployment
```

### Option 2: CloudFormation Stack Rollback

```bash
# Roll back to previous stack version
aws cloudformation continue-update-rollback \
  --stack-name pixel-prompt-production

# Or delete and redeploy from known good commit
aws cloudformation delete-stack \
  --stack-name pixel-prompt-production

# Wait for deletion, then re-run deployment workflow from good commit
```

### Option 3: Manual Deployment (Emergency)

```bash
# Clone repository at last known good commit
git checkout <good-commit-sha>

# Deploy manually
cd backend
sam deploy \
  --stack-name pixel-prompt-production \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    Model1Key="$MODEL_1_KEY" \
    # ... (other keys)
```

## Troubleshooting

### "Deployment requires approval but no reviewers configured"

**Solution**: Add required reviewers to production environment:
1. Settings > Environments > production
2. Click **Required reviewers**
3. Add maintainer GitHub usernames
4. Save changes

### "AWS credentials not configured"

**Solution**: Verify secrets in production environment:
1. Settings > Environments > production > Secrets
2. Ensure `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are set
3. Or check repository secrets if not using environment-specific secrets

### "Stack already exists in CREATE_FAILED state"

**Solution**: Delete failed stack and retry:
```bash
aws cloudformation delete-stack --stack-name pixel-prompt-production
aws cloudformation wait stack-delete-complete --stack-name pixel-prompt-production
# Re-run deployment workflow
```

### "Health checks failing after deployment"

**Investigation**:
1. Check CloudWatch logs for Lambda errors
2. Verify API Gateway endpoint responding
3. Check S3 bucket permissions
4. Verify all API keys configured correctly

**Solution**: If critical, initiate rollback procedure

## Security Considerations

1. **Approval Required**: Never bypass production environment approval
2. **Review Changes**: Carefully review diff before approving deployment
3. **Secrets Management**: Rotate production API keys quarterly
4. **Least Privilege**: Production AWS credentials should have minimal required permissions
5. **Audit Trail**: All deployments logged in workflow runs and CloudFormation events

## Production Deployment Checklist

Before approving production deployment:

- [ ] Staging deployment successful and verified
- [ ] All tests passing in CI
- [ ] Security scans passing (no high/critical vulnerabilities)
- [ ] Changelog updated with changes
- [ ] Breaking changes documented
- [ ] Database migrations applied (if applicable)
- [ ] Backup of critical data taken (if applicable)
- [ ] Stakeholders notified of planned deployment
- [ ] Rollback plan documented
- [ ] On-call engineer available for monitoring

After production deployment:

- [ ] API endpoint responding correctly
- [ ] Health checks passing
- [ ] No errors in CloudWatch logs (first 10 minutes)
- [ ] All features tested manually
- [ ] Performance metrics within acceptable range
- [ ] Stakeholders notified of successful deployment
- [ ] Documentation updated with new URLs (if changed)

## Release Versioning

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** version (v2.0.0): Incompatible API changes
- **MINOR** version (v1.1.0): Backwards-compatible new features
- **PATCH** version (v1.0.1): Backwards-compatible bug fixes

Example changelog:
```
v1.2.0 - 2025-11-16
- feat: Add new model provider support
- feat: Implement batch image generation
- fix: Resolve rate limiting edge case
- perf: Optimize Lambda cold start time
```

## Useful Commands

```bash
# View production stack status
aws cloudformation describe-stacks --stack-name pixel-prompt-production

# View stack events (deployment progress)
aws cloudformation describe-stack-events --stack-name pixel-prompt-production

# View stack outputs (API endpoint, S3 bucket, etc.)
aws cloudformation describe-stacks \
  --stack-name pixel-prompt-production \
  --query 'Stacks[0].Outputs' \
  --output table

# Tail CloudWatch logs
aws logs tail /aws/lambda/pixel-prompt-production-GenerateFunction --follow

# Test API endpoint
curl -X GET https://your-api-endpoint.com/gallery/list

# Generate test image
curl -X POST https://your-api-endpoint.com/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test", "ip": "1.2.3.4"}'
```

## Contact

For production deployment questions or issues:
- GitHub Issues: Tag with `deployment` and `production`
- Maintainers: See CODEOWNERS file

---

**Last Updated**: 2025-11-16
