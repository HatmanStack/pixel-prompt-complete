# Legal

Drafts and research supporting a paid launch. **Nothing here is legal advice
and nothing here is published yet.** An attorney should review before the
Service charges money.

| Document                                             | Status                        | Blocking launch?                    |
| ---------------------------------------------------- | ----------------------------- | ----------------------------------- |
| [provider-obligations.md](provider-obligations.md)   | Research, complete            | No, but sets what the rest must say |
| [terms-of-service.md](terms-of-service.md)           | Draft, has placeholders       | Yes                                 |
| [privacy-policy.md](privacy-policy.md)               | Draft, has placeholders       | Yes                                 |
| [acceptable-use-policy.md](acceptable-use-policy.md) | Draft, has placeholders       | Yes                                 |
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
   accessed by" under-18s.** Stricter than an affirmation, and currently
   unaddressed: the guest tier needs no account and asks nothing.
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

## Before publishing

- [ ] Fill every `{{PLACEHOLDER}}`
- [ ] Attorney review, covering at minimum the GDPR basis for publication and
      the liability cap
- [ ] Register a DMCA agent for the public gallery
- [ ] Confirm the Gemini key tier and write the matching privacy statement
- [ ] Add an 18+ gate to the guest path
- [ ] Serve these from the app and link them from the footer, checkout, and the
      point of generation
