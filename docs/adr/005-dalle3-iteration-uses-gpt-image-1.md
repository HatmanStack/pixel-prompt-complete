# ADR 005: DALL-E 3 Cannot Edit; Iteration and Outpaint Use `gpt-image-1`

## Status

Accepted

Promoted from `docs/plans/2026-04-06-audit-pixel-prompt/Phase-0.md` (ADR-5).
**The number 005 here is a coincidence, not preservation.** These files are
numbered sequentially from 002 in promotion order; the fact that this decision
kept its old digit is an accident of that order and nothing else. ADR 003 and
ADR 004 in this directory do **not** mean what ADR-3 and ADR-4 meant in the
paid-tier plan, and the other ADR-5 — "Presigned URL Download",
`docs/plans/2026-04-15-ux-enhancements/Phase-0.md:153` — is not this document.
That collision is why citations now carry a path. See [README.md](README.md).

## Context

The product is iterative refinement: generate four images, then refine one
image-to-image. That requires an edit endpoint.

OpenAI's `images.edit` does not accept `dall-e-3`. DALL-E 3 is a
generation-only model. `OPENAI_MODEL_ID` defaults to `dall-e-3` and is the model
an operator configures, so the naive implementation — pass the configured model
id to every OpenAI call — fails on every `/iterate` and `/outpaint`.

Options considered:

1. **Drop OpenAI from the refinement path.** Rejected. Three of four models
   would refine and one would not, for a reason no user can see.
1. **Re-generate from a rewritten prompt instead of editing.** Rejected. It
   discards the source image, which is the entire refinement product: the user
   is asking for a change to _this_ image, not another image about the same
   subject.
1. **Use a different OpenAI model for edits than for generation.** Chosen.

## Decision

`handle_openai` generates with the configured model (`model_config["id"]`,
default `dall-e-3`). `iterate_openai` and `outpaint_openai` call `images.edit`
with the hardcoded constant `_EDIT_MODEL = "gpt-image-1"`, **regardless of
`OPENAI_MODEL_ID`**.

The constant is deliberately not configurable. Making it an environment variable
would let an operator set it to `dall-e-3` and reintroduce exactly the failure
this decision exists to prevent, with no error until a user clicks refine.

## Code Governed

- `backend/src/models/providers/openai_provider.py:32` — `_EDIT_MODEL`
- `backend/src/models/providers/openai_provider.py:97-132` — `iterate_openai`
- `backend/src/models/providers/openai_provider.py:135-180` — `outpaint_openai`
- `tests/backend/unit/test_openai_handler.py` — two tests configured with
  `dall-e-3` that assert the edit calls go to `gpt-image-1` anyway. They are the
  regression guard: this decision is invisible at runtime until it is wrong.

## Consequences

### Positive

- **OpenAI refines like the other three providers.** No per-model gap in the UI.
- **The source image is preserved through refinement**, which is what makes the
  iteration chain mean anything.
- **The failure mode is impossible to reach by configuration.** A hardcoded
  constant cannot be set wrong in a deploy.

### Negative

- **Two models bill under one provider entry.** The cost table carries separate
  `COST_OPENAI_GENERATE_USD_MICROS`, `COST_OPENAI_REFINE_USD_MICROS` and
  `COST_OPENAI_OUTPAINT_USD_MICROS` values partly for this reason: the refine
  cost is not the generate cost.
- **Style discontinuity.** A DALL-E 3 image refined by `gpt-image-1` can shift
  in style in a way the other providers' generate/edit pairs do not.
- **`OPENAI_MODEL_ID` is only half-honoured**, and a reader who does not know
  this ADR will report that as a bug. Hence the four in-code references to it.

### Neutral

- If OpenAI ships an edit endpoint that accepts `dall-e-3`, this decision
  retires and `_EDIT_MODEL` goes away.
