---
type: doc-health
date: 2026-04-06
prevention_scope: markdownlint + lychee
language_stack: Both (JS/TS + Python)
---

# Documentation Audit: pixel-prompt-complete

## Configuration
- **Prevention Scope:** Markdown linting (markdownlint) + link checking (lychee)
- **Language Stack:** Both JS/TS and Python
- **Constraints:** None

## Summary
- Docs scanned: 5 files (CLAUDE.md, 2 ADRs, backend/.env.example, frontend/.env.example)
- Code modules scanned: 16 backend Python files, 50+ frontend TypeScript files, 1 SAM template, 1 CI workflow
- Findings: 7 drift, 2 gaps, 2 stale, 0 broken links, 3 config drift, 1 structure issue

## Findings

### DRIFT (doc exists, doesn't match code)

1. **`CLAUDE.md:49`** — CI trigger branches
   - Doc says: "Runs on push/PR to main/develop"
   - Code says (`.github/workflows/ci.yml:3-8`): Only triggers on `main`, no `develop` branch. The word "develop" does not appear in the CI config.

2. **`CLAUDE.md:209`** — S3 Structure shows `gallery/{timestamp}/`
   - Doc says: `gallery/{timestamp}/` for gallery images with metadata
   - Code says (`storage.py:138-167`): Galleries are stored under `sessions/{timestamp}/` prefix, NOT `gallery/`. The `list_galleries` method lists from `sessions/` prefix and filters by timestamp regex. There is **no `gallery/` prefix** anywhere in the codebase.
   - **This is a significant documentation lie.** The S3 structure section implies a separate `gallery/` prefix that does not exist.

3. **`CLAUDE.md:269`** — Frontend version claims
   - Doc says: "Tailwind CSS 4, Vite 7, Vitest 1"
   - Code says (`frontend/package.json`): `@tailwindcss/postcss: ^4.2.2` (Tailwind 4 confirmed), `vite: ^8.0.0` (Vite **8**, not 7), `vitest: ^4.1.0` (Vitest **4**, not 1)
   - **Drift**: Vite is 8.x not 7.x, Vitest is 4.x not 1.x.

4. **`CLAUDE.md:89`** — `/log` endpoint not in SAM template
   - The `/log` endpoint is handled in code (`lambda_function.py:252`) but is **not defined as a SAM event** in `backend/template.yaml`. It works only because the Lambda catch-all routing handles it, but it's not a formally declared API Gateway route. The template only declares: /generate, /iterate, /outpaint, /status/{sessionId}, /enhance, /gallery/list, /gallery/{sessionId}. The `/log` endpoint is missing from the SAM template.

5. **`CLAUDE.md:84`** — Outpaint presets listed
   - Doc says: presets are "16:9, 9:16, 1:1, 4:3, expand_all"
   - Code says (`lambda_function.py:585`): `valid_presets = ["16:9", "9:16", "1:1", "4:3", "expand_all"]`
   - **Match confirmed** — no actual drift here.

6. **`CLAUDE.md:190`** — Handler signature for generate handlers
   - Doc says: `handle_<provider>(config, prompt, params)`
   - Code says (`handlers.py:114`): `HandlerFunc = Callable[[ModelConfig, str, GenerationParams], HandlerResult]`
   - The doc uses "config" loosely but the actual first parameter is `ModelConfig` (a `Dict[str, Any]`), not a `ModelConfig` dataclass. Minor imprecision.

7. **`CLAUDE.md:191`** — Iterate handler signature
   - Doc says: `iterate_<provider>(config, source_image, prompt, context)`
   - Code says (`handlers.py:115`): `IterateHandlerFunc = Callable[[ModelConfig, bytes, str, List[Dict[str, Any]]], HandlerResult]`
   - Doc omits that `source_image` is typed as `Union[str, bytes]` in actual implementations. Minor inconsistency.

### GAPS (code exists, no doc)

1. **`lambda_function.py:57-67`** — Request body size limits and reserved log metadata keys
   - `MAX_BODY_SIZE = 1_048_576` (1 MB) and `MAX_LOG_BODY_SIZE = 10_240` (10 KB) are enforced but not documented anywhere.
   - `_RESERVED_LOG_METADATA_KEYS` sanitization behavior is undocumented.

2. **`frontend/.env.example:24-27`** — `VITE_DEBUG` and `VITE_API_TIMEOUT` env vars
   - Listed as optional in the frontend `.env.example` but not documented in CLAUDE.md's Frontend environment variables table. Neither variable is actually read by any frontend source code (`frontend/src/`), making them phantom config — documented in `.env.example` but not implemented.

### STALE (doc exists, code doesn't)

1. **`docs/adr/001-fixed-four-models.md:27`** — Legacy ModelRegistry
   - ADR says: "The legacy `ModelRegistry` class remains in `models/registry.py` (unused but not yet removed)"
   - Reality: `backend/src/models/registry.py` does **not exist**. The file was apparently removed after the ADR was written, but the ADR was not updated.

2. **`CLAUDE.md:209`** — S3 `gallery/{timestamp}/` prefix
   - As noted in DRIFT #2, this prefix does not exist. Gallery images are stored under `sessions/{timestamp}/`, the same prefix as session data. The documented `gallery/` prefix is entirely fictional.

### BROKEN LINKS

No broken internal links found. The docs are self-contained with no cross-references between markdown files.

### STALE CODE EXAMPLES

No stale import paths or code examples found. The code blocks in CLAUDE.md are command-line examples and directory trees, which are structurally accurate (matching actual file layout).

### CONFIG DRIFT

1. **`VITE_DEBUG` and `VITE_API_TIMEOUT`** — Documented in `frontend/.env.example` (lines 24, 27) but no frontend source code reads these variables. They are phantom configuration.

2. **`frontend/src/vite-env.d.ts`** declares types for `VITE_CLOUDFRONT_DOMAIN`, `VITE_S3_BUCKET`, `VITE_ENVIRONMENT` — these are typed but never actually read by application code (only `VITE_API_ENDPOINT` is used, in `api/config.ts:7`). The CLAUDE.md documents them as frontend env vars, but they serve no runtime purpose.

3. **Missing SAM template route for `/log`** — The `/log` POST endpoint is handled by `lambda_function.py` routing logic but has no corresponding `Events` entry in `backend/template.yaml`. This means it relies on a catch-all or implicit routing rather than explicit API Gateway configuration.

### STRUCTURE ISSUES

1. **No drift prevention tooling installed** — Neither `.markdownlint*` config files nor `lychee*` config files exist in the repository. No CI step runs markdown linting or link checking. These tools are not configured.
