# Provider terms: what flows down to Pixel Prompt

Reviewed 2026-07-25 against the four enabled providers, for the question that
gates a paid launch: **may we charge money for output generated through these
APIs, and what conditions come attached?**

Not legal advice. This is an engineering read of published terms, done to find
blockers and obligations. An attorney should review before charging money,
particularly the age and publication findings below.

## Short answer

The business model is **not** invalidated. All four providers assign output
rights to the customer and permit commercial use. No provider forbids building
a paid application on their API.

Three conditions do attach, and one product behaviour is a larger exposure than
anything in the provider terms.

## Output rights, by provider

| Provider                        | Output rights                 | Commercial use             | Indemnity                |
| ------------------------------- | ----------------------------- | -------------------------- | ------------------------ |
| OpenAI (DALL-E 3 / gpt-image-1) | Assigned to customer          | Yes                        | No                       |
| Google Gemini                   | Google claims no ownership    | Yes, same on free and paid | No                       |
| Amazon Nova Canvas              | Customer owns output          | Yes                        | Yes, via AWS             |
| Adobe Firefly                   | Customer may use commercially | Yes                        | Yes, on qualifying plans |

All four prohibit using output to **train competing models**. Pixel Prompt does
not train anything, so this is clear today. It is a boundary worth remembering:
the model-preference counters added recently are aggregate integers, not
training data, but if that signal were ever used to train a routing model on
provider output, this clause is the one to re-read first.

Indemnity is asymmetric and worth understanding rather than relying on. Firefly
and Nova carry vendor backing; Gemini and OpenAI do not. If a user receives a
copyright claim over an image, only two of the four have anything behind them,
and Adobe's is plan-dependent. Pixel Prompt should not repeat any provider's
"commercially safe" marketing as its own promise.

## Condition 1: Gemini's free tier is a data-sharing tier

From the Gemini API Additional Terms of Service:

> **Unpaid Services:** Google uses the content you submit to the Services and
> any generated responses to provide, improve, and develop Google products and
> services [...] human reviewers may read, annotate, and process your API input
> and output.
>
> **Paid Services:** Google doesn't use your prompts [...] or responses to
> improve our products.

If the deployed `GEMINI_API_KEY` is on the unpaid tier, then **every prompt and
every generated image passing through Gemini becomes Google training data, and
may be read by a human reviewer.** That is a defensible choice for a hobby
deployment and an indefensible one for a paid product whose privacy policy says
otherwise.

This is not visible in the code. It is a property of the key's billing status
in Google Cloud, so no test can catch it and no config flag records it.

**Action:** confirm the production key is on the paid tier before launch, and
treat it as a deploy checklist item rather than an assumption. If it stays
unpaid, the privacy policy must say so plainly.

## Condition 2: Google requires 18+, and more than an affirmation

This is the strictest term across the four providers and it binds the whole
product, because it is not limited to the individual user:

> You must be 18 years of age or older to use the APIs. You also will not use
> the Services as part of a website, application, or other service [...] that
> is directed towards or is likely to be accessed by individuals under the age
> of 18.

"Likely to be accessed by" is a materially harder test than "you promised you
were 18." Pixel Prompt today is a public URL with a **guest tier that requires
no account at all** — the lowest-friction path to an AI image generator, which
is close to a description of what an under-18 audience finds. Nothing in the
product currently asks.

Meeting a "likely to be accessed by" standard also implicates COPPA in the US
and the UK Age Appropriate Design Code, both of which look at the actual
audience rather than the stated one.

**Action:** the Terms must set 18+ as a condition of use, and the guest path
needs an age affirmation before first generation, not buried in a footer link.
This is a code change, not just a document. It is tracked as a follow-up rather
than done here, because it changes the guest funnel and that is a product call.

## Condition 3: Nova watermarks everything, invisibly

From the Nova Canvas AWS AI Service Card:

> Amazon Nova Canvas applies an invisible watermark to all images it generates.

Not optional and not configurable. Any image a user generates through Nova is
detectable as AI-generated by Amazon's detection API, permanently.

This is not a blocker and arguably a feature. It matters because Pixel Prompt
sells output to people who may use it commercially, and one of the four models
silently marks its output in a way the others do not. Saying so is cheap;
having a user discover it after building on the image is not.

**Action:** disclose in the Terms. No code change.

## The larger exposure is ours, not theirs

Every provider term above is satisfiable. The bigger problem is a product
behaviour that no provider requires and nothing currently discloses.

**Pixel Prompt publishes every prompt and every generated image, to everyone,
with no notice and no way to opt out.**

Traced through the code:

- `ImageStorage.upload_image` writes to `sessions/{target}/`, where `target` is
  `datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")`
  (`lambda_function.py:744`, `:1136`).
- `ImageStorage.list_galleries` returns every folder matching
  `^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}$` (`storage.py:146`). That regex matches
  the format above exactly, so every generated image is a gallery entry.
- `GET /gallery/list` and `GET /gallery/{sessionId}` carry **no authorizer**,
  so the whole corpus is enumerable by anyone on the internet.
- `PromptHistoryRepository.record_prompt` "always writes a global feed item
  (`GLOBAL#RECENT`)", served by `GET /prompts/recent`, also **unauthenticated**.

There is no `visibility` field, no `private` flag, and no opt-out anywhere in
`backend/src/`. There is no user-facing notice anywhere in the frontend.

A public gallery is a legitimate and probably deliberate feature; it drives
discovery and it is most of what makes the landing page interesting. The
problem is not that it exists. The problem is:

1. **Nobody is told.** No terms, no privacy policy, no UI notice.
2. **Prompts are free text.** People type names, locations, employers, personal
   situations, and unreleased ideas into them. Publishing that without notice is
   a disclosure of personal data under GDPR and CCPA with no legal basis and no
   notice, independent of the images.
3. **Paying changes the expectation.** Users who pay for a creative tool
   generally assume their work is private by default. Charging while publishing
   silently is the kind of gap that produces a refund wave and a news cycle
   rather than a lawsuit, which is worse for a small product.
4. **Hosting public UGC creates obligations** — DMCA agent registration and
   takedown process, and moderation of what appears on a page we serve.

**Resolved: public on free tiers, private on paid.** Privacy became a paid
benefit rather than a setting, which keeps the discovery loop that makes the
gallery worth visiting while giving paying users what they already assume they
are getting.

Implemented structurally rather than as a filter applied on read. A paid
generation is written under a `private/` prefix that the CloudFront origin
policy does not grant, so it has no unsigned URL to leak; reaching it requires
a presigned URL the Lambda issues only after checking ownership. Every path
that can reach a session — `/status`, `/download`, `/iterate`, `/outpaint` —
authorizes it, and private prompts are not written to the global feed. See
`test_session_visibility.py`, which enumerates those paths deliberately.

Two things surfaced while implementing it that were bugs in their own right:

- Image keys contained no session id, so two sessions starting in the same UTC
  second shared a gallery folder and, for the same model, produced an identical
  key and silently overwrote each other. At 500 generates/day that was a 76%
  chance of happening on any given day.
- The S3 lifecycle rule was scoped to `sessions/`, so the new `private/` prefix
  would have been retained forever, contradicting the 30-day deletion this
  policy states.

The existing corpus was generated before any of this and remains public. It
ages out under the 30-day lifecycle rule.

## Deploy checklist

Items that cannot be verified from the repository and must be confirmed by the
operator:

- [ ] `GEMINI_API_KEY` is on the **paid** tier (Condition 1)
- [ ] Firefly plan status, if the indemnity is being relied on at all
- [ ] DMCA agent registered with the US Copyright Office, if hosting public UGC
- [ ] Stripe account business details and refund policy match the published Terms

## Sources

- [Gemini API Additional Terms of Service](https://ai.google.dev/gemini-api/terms)
- [OpenAI Service terms](https://openai.com/policies/service-terms/)
- [OpenAI Business terms](https://openai.com/policies/nov-2023-business-terms/)
- [Amazon Nova Canvas AI Service Card](https://docs.aws.amazon.com/ai/responsible-ai/nova-canvas/overview.html)
- [AWS Service Terms](https://aws.amazon.com/service-terms/)
- [Adobe Firefly API overview](https://developer.adobe.com/firefly-services/docs/firefly-api/)
- [Adobe Firefly commercial approach](https://business.adobe.com/products/firefly-business/firefly-ai-approach.html)
