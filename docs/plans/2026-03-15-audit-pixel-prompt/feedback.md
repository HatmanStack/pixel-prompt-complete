# Feedback Channel

## Active Feedback

### [PLAN_REVIEW] Add `format:check` to Phase 0 verification commands
- **Phase:** Phase-0
- **Task:** Verification Commands
- **Severity:** SUGGESTION
- **Description:** Phase 0 mentions Prettier via `npm run format:check` as a frontend convention, and CI runs `format:check` (confirmed in `.github/workflows/ci.yml` line 24). However, the Verification Commands section at the bottom of Phase 0 only lists `npm run lint` and `npm run typecheck` -- it omits `npm run format:check`. Add `npm run format:check` to the frontend verification commands block so the implementer catches formatting issues locally before CI does.
- **Status:** OPEN

### [PLAN_REVIEW] Prefer shared utility over importing private functions in Phase 2 Task 3
- **Phase:** Phase-2
- **Task:** Task 3
- **Severity:** SUGGESTION
- **Description:** The plan suggests importing `_get_openai_client` and `_get_genai_client` (underscore-prefixed private functions) from `handlers.py` into `enhance.py`, with a fallback to create a shared utility if circular imports arise. Importing private functions across module boundaries is poor practice regardless of whether it causes circular imports. Consider making the primary instruction to extract these cached client factories into `utils/clients.py` (or rename them without the underscore prefix), and treat the cross-module private import as the fallback, not the primary approach.
- **Status:** OPEN

### [PLAN_REVIEW] Line numbers in Phase 1 Task 3 may drift after Tasks 1-2
- **Phase:** Phase-1
- **Task:** Task 3
- **Severity:** SUGGESTION
- **Description:** Task 3 references specific line numbers in `handlers.py` (lines 39-40, 64-83) and `config.py` (line 51, 52). Tasks 1 and 2 also modify `config.py`, so line numbers will shift. The plan already provides function/variable names alongside line numbers, which is good. Consider adding a note like "Line numbers are approximate; search by function/variable name" to prevent implementer confusion.
- **Status:** OPEN

### [CODE_REVIEW] Task 3: handle_iterate and handle_outpaint still exceed 30-line target
- **Phase:** Phase-3
- **Task:** Task 3
- **Severity:** SUGGESTION
- **Description:** The Phase-3 Task 3 verification checklist specifies "handle_iterate and handle_outpaint are significantly shorter (each <30 lines)." Currently handle_iterate is 68 lines and handle_outpaint is 71 lines. The implementer extracted `_validate_refinement_request` and `_load_source_image` as shared helpers, which is good, but did not create the unified `_handle_refinement` function described in the spec. The result branching (success/failure with `_handle_successful_result`/`_handle_failed_result`) and the `try/except` error handling boilerplate are still duplicated between both handlers. Consider extracting the common dispatch-and-result-handling flow into a shared function that accepts a callable for the unique handler invocation, which would bring both handlers under 30 lines.
- **Status:** OPEN

### [CODE_REVIEW] Dead json.JSONDecodeError catches in all three POST handlers
- **Phase:** Phase-3
- **Task:** Task 1
- **Severity:** SUGGESTION
- **Description:** After extracting `_parse_and_validate_request`, the `except json.JSONDecodeError` blocks in `handle_generate` (line 355), `handle_iterate` (line 478), and `handle_outpaint` (line 551) are now unreachable dead code. JSON parsing is handled entirely within `_parse_and_validate_request`, so the `try` blocks in these handlers can never raise `json.JSONDecodeError`. These dead catches should be removed to avoid confusion and reduce handler line counts.
- **Status:** OPEN

## Resolved Feedback

<!-- Move resolved items here with a resolution note -->
<!--
### [SOURCE_TAG] Item Title
- **Phase:** Phase-N
- **Task:** Task N
- **Resolution:** What was done to address this
- **Status:** RESOLVED
-->
