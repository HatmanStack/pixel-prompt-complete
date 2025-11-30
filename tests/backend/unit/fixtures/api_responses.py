"""
Mock API responses for testing model handlers
"""

import base64

# Sample base64-encoded image data (1x1 PNG)
SAMPLE_IMAGE_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

# OpenAI DALL-E 3 Response
OPENAI_DALLE3_RESPONSE = {
    "data": [
        {
            "url": "https://example.com/generated-image.png",
            "revised_prompt": "A beautiful sunset over mountains with vibrant colors"
        }
    ]
}

# Google Gemini Response
GOOGLE_GEMINI_RESPONSE = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": SAMPLE_IMAGE_BASE64
                        }
                    }
                ]
            }
        }
    ]
}

# Google Imagen Response
GOOGLE_IMAGEN_RESPONSE = {
    "predictions": [
        {
            "bytesBase64Encoded": SAMPLE_IMAGE_BASE64,
            "mimeType": "image/png"
        }
    ]
}

# AWS Bedrock Nova Canvas Response
BEDROCK_NOVA_RESPONSE = {
    "images": [
        SAMPLE_IMAGE_BASE64
    ]
}

# AWS Bedrock Stable Diffusion Response
BEDROCK_SD_RESPONSE = {
    "artifacts": [
        {
            "base64": SAMPLE_IMAGE_BASE64,
            "finishReason": "SUCCESS"
        }
    ]
}

# Stability AI Response
STABILITY_AI_RESPONSE = {
    "artifacts": [
        {
            "base64": SAMPLE_IMAGE_BASE64,
            "finishReason": "SUCCESS"
        }
    ]
}

# Black Forest Labs (Flux) Response
BLACK_FOREST_RESPONSE = {
    "id": "test-generation-id",
    "status": "Ready",
    "result": {
        "sample": f"data:image/png;base64,{SAMPLE_IMAGE_BASE64}"
    }
}

# Recraft Response
RECRAFT_RESPONSE = {
    "data": [
        {
            "url": f"data:image/png;base64,{SAMPLE_IMAGE_BASE64}"
        }
    ]
}

# Generic OpenAI-compatible Response
GENERIC_OPENAI_RESPONSE = {
    "data": [
        {
            "url": "https://example.com/image.png"
        }
    ]
}

# Error Responses
ERROR_RATE_LIMIT = {
    "error": {
        "message": "Rate limit exceeded",
        "type": "rate_limit_error",
        "code": "rate_limit_exceeded"
    }
}

ERROR_UNAUTHORIZED = {
    "error": {
        "message": "Invalid API key",
        "type": "invalid_request_error",
        "code": "invalid_api_key"
    }
}

ERROR_TIMEOUT = {
    "error": {
        "message": "Request timeout",
        "type": "timeout_error"
    }
}

# Sample Image Content (for download testing)
SAMPLE_IMAGE_CONTENT = base64.b64decode(SAMPLE_IMAGE_BASE64)
