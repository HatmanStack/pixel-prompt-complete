# Feedback Channel

## Active Feedback

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

### [PLAN_REVIEW] Add `format:check` to Phase 0 verification commands
- **Phase:** Phase-0
- **Task:** Verification Commands
- **Resolution:** Added `npm run format:check` to Phase-0 frontend verification commands block
- **Status:** RESOLVED

---

### [PLAN_REVIEW] Prefer shared utility over importing private functions in Phase 2 Task 3
- **Phase:** Phase-2
- **Task:** Task 3
- **Resolution:** Updated Phase-2 Task 3 to use public `utils/clients.py` factories (`get_openai_client`, `get_genai_client`) instead of importing private `_get_*` functions from handlers.py
- **Status:** RESOLVED

---

### [PLAN_REVIEW] Line numbers in Phase 1 Task 3 may drift after Tasks 1-2
- **Phase:** Phase-1
- **Task:** Task 3
- **Resolution:** Added note to Phase-1 Task 3 that line numbers are approximate and to search by function/variable name. Changed line references to "approximately" throughout.
- **Status:** RESOLVED

---
