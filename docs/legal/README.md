# Legal

Drafts and research supporting a paid launch. **Nothing here is legal advice
and nothing here is published yet.** An attorney should review before the
Service charges money.

| Document                                             | Status                        | Blocking launch?                         |
| ---------------------------------------------------- | ----------------------------- | ---------------------------------------- |
| [provider-obligations.md](provider-obligations.md)   | Research, complete            | No, but sets what the rest must say      |
| [terms-of-service.md](terms-of-service.md)           | Draft, has placeholders       | Yes                                      |
| [privacy-policy.md](privacy-policy.md)               | Draft, has placeholders       | Yes                                      |
| [acceptable-use-policy.md](acceptable-use-policy.md) | Draft, has placeholders       | Yes                                      |
| [dmca-policy.md](dmca-policy.md)                     | Draft, needs registered agent | Yes, the free-tier gallery is public UGC |

## What the research found

The business model is sound. All four providers permit commercial use of
output, so charging for generated images is not blocked by anyone's terms. The
mechanism differs (assignment, ownership, licence, or simply no ownership
claim) and the drafts should not flatten that into "they assign it to you".

Three conditions attach, detailed in
[provider-obligations.md](provider-obligations.md):

1. **The paid Gemini tier is mandatory.** Google's terms permit only Paid
   Services when making an API client available to users in the EEA,
   Switzerland, or the UK, and the app is not geo-restricted. The unpaid tier
   would also make every prompt and image Google training data readable by a
   human reviewer. Not visible from the code — it depends on the key's billing
   status.
2. **Google requires 18+, and requires that the Service not be "likely to be
   accessed by" under-18s.** Stricter than an affirmation. The obligation has
   not changed; its status has. An 18+ gate now runs before a first generation
   on **every** tier including guest — `_enforce_age_gate` in
   `backend/src/lambda_function.py`, called from request validation on
   `/generate` and refusing with `403` until the caller sends
   `ageAffirmed: true`. `AGE_GATE_ENABLED` (`backend/src/config.py:98`) defaults
   **on**, the only flag in that file that does, so an operator who configures
   nothing gets the compliant behaviour. Refinement is not separately gated
   because it requires a session, which required a generation, which required
   this. An affirmation still falls short of the "not likely to be accessed by"
   test on its own; it is the part of that test the Service can implement.
3. **Nova Canvas invisibly watermarks every image it generates.** Not optional.
   Disclosure item only.

## The finding that drove a product change

The Service used to publish every prompt and every generated image, to
everyone, with no notice and no opt-out — including on paid tiers.
`/gallery/list`, `/gallery/{sessionId}` and `/prompts/recent` are all
unauthenticated, every generation wrote to a gallery folder, and every prompt
wrote to a global feed. There was no `visibility` field anywhere in the backend
and no notice anywhere in the frontend.

**Resolved: public on free tiers, private on paid.** Privacy is a paid benefit.
Free and signed-out generations still feed the public gallery, which is what
makes it worth browsing; paid generations are stored where they have no public
address at all and are served through short-lived signed links after an
ownership check.

The drafts here describe that behaviour. If the tier boundary moves, Section 5
of the Terms and "What is public" in the Privacy Policy are the two places that
have to move with it.

Verified against the code as it stands: `_PRIVATE_TIERS` in
`backend/src/lambda_function.py` is exactly `{"paid"}`, and private images are
written under `PRIVATE_PREFIX = "private"`
(`backend/src/utils/storage.py`). The bucket policy grants the CloudFront
origin-access identity `sessions/*` and nothing else, so a private object has
no unsigned CDN URL at all rather than an unadvertised one.

One correction to the record: that private path was **non-functional in
deployment** until the Lambda execution role was granted the `private/*` prefix.
The documented behaviour was correct all along; the IAM grant was not, and paid
generation failed with AccessDenied on every request. The drafts did not need to
change — the deployment did.

## Before publishing

- [ ] Fill every `{{PLACEHOLDER}}`
- [ ] Attorney review, covering at minimum the GDPR basis for publication and
      the liability cap
- [ ] Register a DMCA agent for the public gallery
- [ ] Confirm the Gemini key tier and write the matching privacy statement
- [x] Add an 18+ gate to the guest path — `_enforce_age_gate` in
      `backend/src/lambda_function.py`, applied at request validation to every
      tier on `/generate`, on by default via `AGE_GATE_ENABLED`
- [ ] Serve these from the app and link them from the footer, checkout, and the
      point of generation
