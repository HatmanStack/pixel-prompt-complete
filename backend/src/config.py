"""
Configuration module for Pixel Prompt Complete Lambda function.
Loads and validates environment variables for model configuration,
AWS credentials, rate limiting, and S3/CloudFront settings.
"""

import os

# AWS credentials for Bedrock
aws_id = os.environ.get('AWS_ACCESS_KEY_ID')
aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY')
aws_region = os.environ.get('AWS_REGION', 'us-west-2')

# S3 and CloudFront
s3_bucket = os.environ.get('S3_BUCKET')
cloudfront_domain = os.environ.get('CLOUDFRONT_DOMAIN')

# Rate limiting
global_limit = int(os.environ.get('GLOBAL_LIMIT', 1000))
ip_limit = int(os.environ.get('IP_LIMIT', 50))
ip_include_str = os.environ.get('IP_INCLUDE', '')
ip_include = [ip.strip() for ip in ip_include_str.split(',') if ip.strip()]

# Model configuration
model_count = int(os.environ.get('MODEL_COUNT', 9))
prompt_model_index = int(os.environ.get('PROMPT_MODEL_INDEX', 1))

# Load all models from environment variables (new 5-field format)
models = []
for i in range(1, model_count + 1):
    provider = os.environ.get(f'MODEL_{i}_PROVIDER', '')
    model_id = os.environ.get(f'MODEL_{i}_ID', '')
    api_key = os.environ.get(f'MODEL_{i}_API_KEY', '')
    base_url = os.environ.get(f'MODEL_{i}_BASE_URL', '')
    user_id = os.environ.get(f'MODEL_{i}_USER_ID', '')

    # Only add if provider and model ID are provided
    if provider and model_id:
        model_config = {
            'index': i,
            'provider': provider,
            'id': model_id,
        }
        # Only include optional fields if they're not empty
        if api_key:
            model_config['api_key'] = api_key
        if base_url:
            model_config['base_url'] = base_url
        if user_id:
            model_config['user_id'] = user_id

        models.append(model_config)

# Validation - warn but don't fail if model count doesn't match
# (allows partial configuration for testing)
if len(models) != model_count:
    pass  # Warning stripped

if len(models) > 0 and (prompt_model_index < 1 or prompt_model_index > len(models)):
    pass  # Warning stripped

# Permanent negative prompt for Stable Diffusion models
perm_negative_prompt = "ugly, blurry, low quality, distorted"
