# Debugging Prompt Enhancement

This guide helps you diagnose and fix issues with the prompt enhancement feature.

## Quick Start

1. **Run diagnostics:**
   ```bash
   ./scripts/diagnose-enhance.sh <stack-name>
   ```

2. **Test the endpoint:**
   ```bash
   ./scripts/test-enhance-endpoint.sh <api-endpoint>
   ```

3. **Check CloudWatch logs:**
   ```bash
   sam logs --stack-name <stack-name> --tail
   ```

## Understanding the Logs

The enhanced logging uses `[ENHANCE]` and `[REGISTRY]` prefixes for easy filtering.

### Initialization Logs (Lambda Cold Start)

When Lambda starts, you'll see:

```
[REGISTRY] Model registry initialized with 9 models
[REGISTRY] Prompt enhancement model (index 1): gpt-4o-mini (provider: openai)
```

**If you see warnings:**
```
[REGISTRY] WARNING: PROMPT_MODEL_INDEX 5 is out of range (1-3)
[REGISTRY] This will cause prompt enhancement to fail!
```
→ **Fix:** Set `PromptModelIndex` to a valid value (1 to MODEL_COUNT)

### Enhancement Request Logs

When `/enhance` is called:

```
[ENHANCE] Starting enhancement for prompt: 'a cat...'
[ENHANCE] Found prompt model: gpt-4o-mini
[ENHANCE] Provider: openai
[ENHANCE] Has API key: True
[ENHANCE] Has base URL: False
[ENHANCE] Using OpenAI-compatible client for provider: openai
[ENHANCE] Using default OpenAI model: gpt-4o-mini
[ENHANCE] Calling OpenAI-compatible API...
[ENHANCE] OpenAI response received: 156 characters
[ENHANCE] SUCCESS!
[ENHANCE] Original: a cat
[ENHANCE] Enhanced: A photorealistic portrait of a fluffy orange tabby cat...
```

## Common Issues & Solutions

### Issue 1: No Prompt Model Configured

**Logs:**
```
[ENHANCE] ERROR: No prompt model configured!
[ENHANCE] PROMPT_MODEL_INDEX: 5
[ENHANCE] Available models: 3
[ENHANCE] Returning original prompt (no enhancement)
```

**Cause:** `PROMPT_MODEL_INDEX` points to a model that doesn't exist.

**Fix:**
```bash
sam deploy --parameter-overrides PromptModelIndex=1
```

---

### Issue 2: No API Key

**Logs:**
```
[ENHANCE] Found prompt model: gpt-4o-mini
[ENHANCE] Provider: openai
[ENHANCE] Has API key: False
[ENHANCE] ERROR: No API key configured for provider: openai
[ENHANCE] Returning original prompt
```

**Cause:** The model is configured but missing an API key.

**Fix:**
```bash
sam deploy --parameter-overrides \
  Model1Provider="openai" \
  Model1Id="gpt-4o-mini" \
  Model1ApiKey="sk-your-api-key-here"
```

---

### Issue 3: API Error

**Logs:**
```
[ENHANCE] Calling OpenAI-compatible API...
[ENHANCE] EXCEPTION occurred: AuthenticationError
[ENHANCE] Error message: Incorrect API key provided
[ENHANCE] Traceback: ...
[ENHANCE] Returning original prompt due to error
```

**Cause:** Invalid API key or API error.

**Fix:**
- Verify API key is correct
- Check API provider status
- Ensure sufficient quota/credits

---

### Issue 4: Wrong Provider Type

**Logs:**
```
[ENHANCE] Found prompt model: dall-e-3
[ENHANCE] Provider: openai
[ENHANCE] Using default OpenAI model: gpt-4o-mini
[ENHANCE] Calling OpenAI-compatible API...
[ENHANCE] EXCEPTION occurred: NotFoundError
[ENHANCE] Error message: Model dall-e-3 does not exist
```

**Cause:** Image generation model configured for text generation task.

**Fix:** Use a text/chat model for enhancement:
```bash
sam deploy --parameter-overrides \
  Model1Provider="openai" \
  Model1Id="gpt-4o-mini" \
  Model1ApiKey="sk-your-api-key"
```

**Supported Models:**
- **OpenAI:** `gpt-4o-mini`, `gpt-4`, `gpt-3.5-turbo`
- **Google Gemini:** `gemini-2.0-flash-exp`, `gemini-1.5-flash`
- **Generic:** Any OpenAI-compatible text model

---

## Filtering CloudWatch Logs

**View only enhancement logs:**
```bash
sam logs --stack-name <stack-name> --tail --filter-pattern "[ENHANCE]"
```

**View initialization logs:**
```bash
sam logs --stack-name <stack-name> --tail --filter-pattern "[REGISTRY]"
```

**View errors only:**
```bash
sam logs --stack-name <stack-name> --tail --filter-pattern "ERROR"
```

---

## Recommended Configuration

For best results with prompt enhancement:

**Option 1: OpenAI (Recommended)**
- Fast, cheap, reliable
- Uses `gpt-4o-mini` automatically
```bash
Model1Provider="openai"
Model1Id="gpt-4o-mini"  # Actually unused, hardcoded to gpt-4o-mini
Model1ApiKey="sk-..."
```

**Option 2: Google Gemini**
- Good quality, free tier available
```bash
Model1Provider="google_gemini"
Model1Id="gemini-2.0-flash-exp"
Model1ApiKey="AIza..."
```

**Option 3: Generic (OpenAI-compatible)**
- For custom/third-party LLMs
```bash
Model1Provider="generic"
Model1Id="llama-3-70b-instruct"
Model1ApiKey="..."
Model1BaseUrl="https://your-api.com/v1"
```

---

## Testing After Fix

After making changes:

1. **Deploy:**
   ```bash
   cd backend && sam build && sam deploy
   ```

2. **Wait for deployment** (30-60 seconds)

3. **Test:**
   ```bash
   ./scripts/test-enhance-endpoint.sh <api-endpoint>
   ```

4. **Check logs:**
   ```bash
   sam logs --stack-name <stack-name> --tail
   ```

You should see `[ENHANCE] SUCCESS!` in the logs if working correctly.

---

## Still Having Issues?

If enhancement still isn't working after following this guide:

1. Share the full `[ENHANCE]` logs from CloudWatch
2. Share your stack configuration (without API keys):
   ```bash
   aws cloudformation describe-stacks \
     --stack-name <stack-name> \
     --query 'Stacks[0].Parameters' \
     --output table
   ```

3. Test the endpoint and share the response:
   ```bash
   ./scripts/test-enhance-endpoint.sh <api-endpoint>
   ```
