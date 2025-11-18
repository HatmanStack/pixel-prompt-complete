# Using AWS Secrets Manager for API Keys

## The Problem
SAM's `--parameter-overrides` resets NoEcho parameters to defaults because API keys aren't saved to samconfig.toml.

## The Solution
Store API keys in AWS Secrets Manager and reference them in template.yaml.

## Setup Steps

### 1. Store API Keys in Secrets Manager

```bash
# Store Google Gemini API key
aws secretsmanager create-secret \
  --name /pixel-prompt/prod/model2-api-key \
  --secret-string "YOUR-GOOGLE-GEMINI-API-KEY" \
  --region us-west-2

# Store other API keys as needed
aws secretsmanager create-secret \
  --name /pixel-prompt/prod/model1-api-key \
  --secret-string "YOUR-OPENAI-API-KEY" \
  --region us-west-2
```

### 2. Update template.yaml

Change the Lambda environment variables to use dynamic references:

```yaml
Environment:
  Variables:
    MODEL_2_API_KEY: !Sub '{{resolve:secretsmanager:/pixel-prompt/prod/model2-api-key}}'
    MODEL_1_API_KEY: !Sub '{{resolve:secretsmanager:/pixel-prompt/prod/model1-api-key}}'
```

### 3. Remove API Key Parameters

You can then remove the ModelXApiKey parameters from template.yaml entirely, or keep them as optional overrides.

### 4. Deploy Safely

Now you can use `--parameter-overrides` without wiping secrets:

```bash
sam deploy --config-env prod --parameter-overrides \
  PromptModelIndex=2 \
  ModelCount=9
```

## Benefits

✅ API keys never reset to defaults
✅ Can use `--parameter-overrides` safely
✅ Secrets managed separately from infrastructure
✅ Can rotate keys without redeploying
✅ IAM controls who can access secrets

## Cost

$0.40/month per secret + $0.05 per 10,000 API calls (very cheap)
