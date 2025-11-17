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

# Load all models from environment variables
models = []
for i in range(1, model_count + 1):
    name = os.environ.get(f'MODEL_{i}_NAME')
    key = os.environ.get(f'MODEL_{i}_KEY')
    if name and key:
        models.append({
            'index': i,
            'name': name,
            'key': key
        })

# Validation - fail fast on misconfiguration
if len(models) != model_count:
    error_msg = f"MODEL_COUNT is {model_count} but only {len(models)} models are configured"
    print(f"ERROR: {error_msg}")
    raise ValueError(error_msg)

if prompt_model_index < 1 or prompt_model_index > len(models):
    error_msg = f"PROMPT_MODEL_INDEX {prompt_model_index} is out of range (1-{len(models)})"
    print(f"ERROR: {error_msg}")
    raise ValueError(error_msg)

# Permanent negative prompt for Stable Diffusion models
perm_negative_prompt = "ugly, blurry, low quality, distorted"

# Print configuration summary at initialization
print("Loaded configuration:")
print(f"  - Models configured: {len(models)}/{model_count}")
print(f"  - S3 Bucket: {s3_bucket}")
print(f"  - CloudFront Domain: {cloudfront_domain}")
print(f"  - Global Rate Limit: {global_limit}/hour")
print(f"  - IP Rate Limit: {ip_limit}/day")
print(f"  - IP Whitelist: {len(ip_include)} IPs")
