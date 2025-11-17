# GitHub Secrets for Deployment

This document lists all GitHub Secrets required for automated deployment workflows.

## Setting Up Secrets

To add secrets to your repository:

1. Go to your repository on GitHub
2. Click **Settings** > **Secrets and variables** > **Actions**
3. Click **New repository secret**
4. Add each secret listed below

## Required Secrets

### AWS Credentials

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `AWS_ACCESS_KEY_ID` | AWS access key for deployment | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | AWS secret access key | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| `AWS_REGION` | AWS region for deployment | `us-east-1` |

**How to create AWS credentials:**
1. Log into AWS Console
2. Go to IAM > Users > Create User
3. Attach policies: `AdministratorAccess` (or more restrictive: CloudFormation, Lambda, S3, API Gateway, CloudFront, IAM)
4. Create access key > Store securely

### AI Provider API Keys

The following secrets are required for AI model providers. Add only the providers you plan to use:

| Secret Name | Provider | Required? | How to Obtain |
|-------------|----------|-----------|---------------|
| `MODEL_1_KEY` | OpenAI | Optional | https://platform.openai.com/api-keys |
| `MODEL_2_KEY` | Google (Gemini/Imagen) | Optional | https://aistudio.google.com/app/apikey |
| `MODEL_3_KEY` | Stability AI | Optional | https://platform.stability.ai/account/keys |
| `MODEL_4_KEY` | Black Forest Labs | Optional | Contact provider |
| `MODEL_5_KEY` | Recraft AI | Optional | https://www.recraft.ai/api-keys |
| `MODEL_6_KEY` | AWS Bedrock (Nova) | Optional | Use AWS credentials |
| `MODEL_7_KEY` | AWS Bedrock (Stable Diffusion) | Optional | Use AWS credentials |
| `MODEL_8_KEY` | Generic Provider 1 | Optional | Provider-specific |
| `MODEL_9_KEY` | Generic Provider 2 | Optional | Provider-specific |

**Note**: At least one model provider API key is required for the application to function.

### Environment-Specific Secrets (Optional)

These are optional and have default values in the SAM template:

| Secret Name | Description | Default | When to Override |
|-------------|-------------|---------|------------------|
| `STACK_NAME_STAGING` | CloudFormation stack name for staging | `pixel-prompt-staging` | If you want a different name |
| `STACK_NAME_PRODUCTION` | CloudFormation stack name for production | `pixel-prompt-production` | If you want a different name |

## Staging vs Production

The deployment workflows support two environments:

- **Staging**: Deployed automatically on merge to `main`
- **Production**: Deployed manually or via release tags, requires approval

You can use the same AWS account and API keys for both environments, or separate them:

### Option 1: Same Credentials (Recommended for Solo Projects)
- Use the same `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `MODEL_*_KEY` secrets
- Staging and production are differentiated by CloudFormation stack name only
- Cost-effective, simpler setup

### Option 2: Separate Credentials (Recommended for Teams)
- Create environment-specific secrets:
  - Staging: `AWS_ACCESS_KEY_ID_STAGING`, `MODEL_1_KEY_STAGING`, etc.
  - Production: `AWS_ACCESS_KEY_ID_PRODUCTION`, `MODEL_1_KEY_PRODUCTION`, etc.
- Modify workflows to use environment-specific secrets
- Better isolation, more secure for production

## Verifying Secrets

After adding secrets, verify them:

1. **Check Secret Names**: Go to Settings > Secrets and variables > Actions
2. **Test Deployment**: Trigger the staging deployment workflow manually (Actions > Deploy Staging > Run workflow)
3. **Check Logs**: If deployment fails, check the workflow logs for missing secrets

## Security Best Practices

1. **Never commit secrets to code**: Always use GitHub Secrets
2. **Rotate credentials regularly**: Update API keys quarterly
3. **Use least privilege**: AWS credentials should have minimal required permissions
4. **Monitor secret usage**: Review GitHub Actions logs for unauthorized access
5. **Use separate production credentials**: For production deployments, use dedicated AWS account or IAM user

## Troubleshooting

### "Error: Credentials could not be loaded"
- Verify `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are set correctly
- Check for extra whitespace in secret values
- Ensure IAM user has necessary permissions

### "Model provider authentication failed"
- Verify the corresponding `MODEL_*_KEY` secret is set
- Check API key is valid (not expired or revoked)
- Ensure API key has correct permissions (e.g., image generation enabled)

### "Stack already exists"
- If you're re-deploying, this is expected (CloudFormation will update)
- If stack is in failed state, delete it manually: `aws cloudformation delete-stack --stack-name <stack-name>`

## Additional Resources

- [GitHub Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [SAM CLI Configuration](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-config.html)

---

**Last Updated**: 2025-11-16
