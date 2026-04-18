---
type: doc-health
scope: All docs, no constraints
language_stack: Both JS/TS and Python
prevention_tooling: Markdown linting (markdownlint) + link checking (lychee)
---

## DOCUMENTATION AUDIT

### SUMMARY
- Docs scanned: 6 files (CLAUDE.md, README.md, backend/.env.example, frontend/.env.example, docs/adr/001-fixed-four-models.md, docs/adr/002-s3-session-state.md)
- Code modules scanned: 30+ Python files, 5+ TypeScript config files
- Total findings: 6 drift, 3 gaps, 3 stale (code comments), 3 config drift

---

### DRIFT (doc exists, doesn't match code)

1. **`README.md:162-173`** — AI Models table completely wrong
   - Doc says 4 models: Flux (BFL, flux-2-pro), Recraft (Recraft, recraftv3), Gemini (Google, gemini-2.5-flash-image), OpenAI (OpenAI, gpt-image-1)
   - Code has 4 models: Gemini (google_gemini, gemini-3.1-flash-image-preview), Nova Canvas (bedrock_nova, amazon.nova-canvas-v1:0), DALL-E 3 (openai, dall-e-3), Firefly (adobe_firefly, firefly-image-5)
   - Model names wrong, provider names wrong, model IDs wrong, env vars wrong
   - Code source: `backend/src/config.py:132-173`

2. **`CLAUDE.md:261-269`** — Frontend environment variables incomplete and incorrect
   - Doc lists: `VITE_API_ENDPOINT`, `VITE_CLOUDFRONT_DOMAIN`, `VITE_S3_BUCKET`, `VITE_ENVIRONMENT`
   - Code actually reads: `VITE_API_ENDPOINT`, `VITE_AUTH_ENABLED`, `VITE_BILLING_ENABLED`, `VITE_COGNITO_DOMAIN`, `VITE_COGNITO_CLIENT_ID`, `VITE_COGNITO_REDIRECT_URI`, `VITE_COGNITO_LOGOUT_URI`, `VITE_ADMIN_ENABLED`, `VITE_CAPTCHA_ENABLED`, `VITE_TURNSTILE_SITE_KEY`
   - Missing variables: `VITE_ADMIN_ENABLED`, `VITE_CAPTCHA_ENABLED`, `VITE_TURNSTILE_SITE_KEY`
   - Documented but not in code: `VITE_CLOUDFRONT_DOMAIN`, `VITE_S3_BUCKET`, `VITE_ENVIRONMENT`
   - Code source: `frontend/src/api/config.ts:7-46`

3. **`CLAUDE.md:102-117`** — API Endpoints table incomplete
   - Doc only lists 11 endpoints; code implements 18+ endpoints
   - Missing endpoints: `/prompts/recent`, `/prompts/history`, `/download/{sessionId}/{model}/{iterationIndex}`, `/admin/users`, `/admin/models`, `/admin/metrics`, `/admin/revenue`
   - Code source: `backend/src/lambda_function.py:378-415`

4. **`README.md:56-64`** — Quick Start port inconsistency
   - README says "Open http://localhost:3000" which matches `vite.config.ts:26`
   - But `frontend/.env.example:17-18` uses port 5173 (Vite default)
   - Code source: `frontend/vite.config.ts:25-29` vs `frontend/.env.example:17-18`

5. **`README.md:170`** — Gemini model ID wrong
   - Doc says: `gemini-2.5-flash-image`
   - Code uses: `gemini-3.1-flash-image-preview`
   - Code source: `backend/src/config.py:140`

6. **`README.md:171`** — OpenAI model ID wrong for generation
   - Doc says: `gpt-image-1` (which is used for iteration, not generation)
   - Code uses for generation: `dall-e-3`
   - Code source: `backend/src/config.py:158`

---

### GAPS (code exists, no documentation)

1. **`/prompts/recent` and `/prompts/history` endpoints** — No mention in CLAUDE.md API table
   - Handlers: `handle_prompts_recent`, `handle_prompts_history`
   - Code source: `backend/src/lambda_function.py:396-398`

2. **`/download/{sessionId}/{model}/{iterationIndex}` endpoint** — No mention in CLAUDE.md API table
   - Code source: `backend/src/lambda_function.py:386-387, 1024-1093`

3. **Admin endpoints** (`/admin/users`, `/admin/models`, `/admin/metrics`, `/admin/revenue`) — No mention in CLAUDE.md API table
   - Code source: `backend/src/lambda_function.py:414-415, 286-355`
   - Frontend config: `frontend/src/api/config.ts:146-149`

---

### STALE (code comments reference removed/incorrect things)

1. **`backend/src/config.py:43`** — Comment lists wrong model names
   - Comment: `'flux', 'recraft', 'gemini', 'openai'`
   - Actual: `'gemini', 'nova', 'openai', 'firefly'`

2. **`backend/src/jobs/manager.py:39`** — Comment lists wrong model names
   - Comment: `4 model columns (flux, recraft, gemini, openai)`
   - Actual: `4 model columns (gemini, nova, openai, firefly)`

3. **`backend/src/jobs/manager.py:125`** — Docstring lists wrong model names
   - Docstring: `Model name ('flux', 'recraft', 'gemini', 'openai')`
   - Actual valid models: `'gemini'`, `'nova'`, `'openai'`, `'firefly'`

---

### BROKEN LINKS
- No broken internal links or missing images detected.

---

### STALE CODE EXAMPLES
- No stale code examples detected in documentation.

---

### CONFIG DRIFT

1. **Frontend `.env.example` uses port 5173 but Vite configured for port 3000**
   - `frontend/.env.example:17-18` uses `http://localhost:5173/`
   - `frontend/vite.config.ts:26` sets `port: 3000`

2. **CLAUDE.md documents non-existent frontend environment variables**
   - Listed as frontend vars: `VITE_CLOUDFRONT_DOMAIN`, `VITE_S3_BUCKET`, `VITE_ENVIRONMENT`
   - Code does not read these; they're backend/infrastructure concerns
   - Code source: `frontend/src/api/config.ts` (no references to these vars)

3. **Missing frontend environment variables in CLAUDE.md frontend vars table**
   - Code reads: `VITE_ADMIN_ENABLED`, `VITE_CAPTCHA_ENABLED`, `VITE_TURNSTILE_SITE_KEY`
   - Not documented in CLAUDE.md:261-269
   - Code source: `frontend/src/api/config.ts:40-46`

---

### STRUCTURE ISSUES

- ADR-001 and ADR-002 are **ACCURATE** and match the codebase
- Documentation hierarchy generally mirrors code structure
- No "Coming Soon" sections or marketing fluff detected

---

### SUMMARY OF ISSUES BY SEVERITY

**Critical (blocks users/contributors):**
- README.md completely wrong about which AI models are supported (lists flux/recraft instead of nova/firefly)
- CLAUDE.md missing 7 API endpoints from the documentation table

**High (documentation misleading):**
- Frontend environment variables in CLAUDE.md are wrong/incomplete (3 phantom vars, 3 missing vars)
- README port number matches code but .env.example doesn't match vite.config.ts

**Medium (stale code comments):**
- 3 locations in backend code still reference "flux" and "recraft" instead of actual models
