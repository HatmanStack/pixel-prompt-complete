# Feedback Channel

## Active Feedback

<!-- No active feedback items -->

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
- **Resolution:** Updated Phase-2 Task 3 to use public `utils/clients.py` factories (`get_openai_client`, `get_genai_client`) instead of importing private `_get_*` functions from handlers.py. Added stronger warning against importing underscore-prefixed private functions across module boundaries.
- **Status:** RESOLVED

---

### [PLAN_REVIEW] Line numbers in Phase 1 Task 3 may drift after Tasks 1-2
- **Phase:** Phase-1
- **Task:** Task 3
- **Resolution:** Strengthened the note in Phase-1 Task 3 to emphasize that all line numbers are approximate and that function/variable names are the authoritative identifiers. Added bold text: "Always search by function/variable name rather than relying on exact line numbers."
- **Status:** RESOLVED

---

### [CODE_REVIEW] Task 3: handle_iterate and handle_outpaint still exceed 30-line target
- **Phase:** Phase-3
- **Task:** Task 3
- **Resolution:** Rewrote Phase-3 Task 3 implementation steps to be more prescriptive about extracting the entire dispatch-try-except-result flow into `_handle_refinement`. Added explicit guidance that wrappers exceeding 15 lines likely have logic that belongs in `_handle_refinement`. Added a verification target note reiterating the <30 line requirement with troubleshooting guidance.
- **Status:** RESOLVED

---

### [CODE_REVIEW] Dead json.JSONDecodeError catches in all three POST handlers
- **Phase:** Phase-3
- **Task:** Task 1
- **Resolution:** Added explicit instruction to Phase-3 Task 1 implementation steps to remove dead `except json.JSONDecodeError` blocks from `handle_generate`, `handle_iterate`, and `handle_outpaint` after extracting JSON parsing into `_parse_and_validate_request`. Explains they are unreachable dead code and that removing them reduces handler line counts.
- **Status:** RESOLVED
