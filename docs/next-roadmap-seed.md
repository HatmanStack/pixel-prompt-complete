# Seed for the next roadmap

Working notes, deliberately uncommitted. Written 2026-07-26 at the end of the
readiness push that produced PRs #153-#167.

Read the divergence section first. It is the part that changes how you plan,
not just what you plan.

## 1. How the last roadmap diverged from what was needed

The previous roadmap was an audit. It read the code that existed and found
real defects in it, and it was largely right about those. What it could not do
is see the things that were **absent**, and nearly everything that turned out
to block monetization was absence-shaped.

Every original P0 was a defect in a built feature:

| Item                                              | Real? | Nature                            |
| ------------------------------------------------- | ----- | --------------------------------- |
| P0-A Stripe cancellation never downgrades         | Yes   | Defect in built code              |
| P0-B Cost ceilings missing on refine paths        | Yes   | Defect in built code              |
| P0-C No price exists                              | Yes   | Not a defect — a missing decision |
| P0-D Default-open flags, anon tier returns `paid` | Yes   | Defect in built code              |

Everything found afterwards was something that did not exist at all:

- **Sessions recorded no owner.** No `ownerId`, no `visibility`, and no
  ownership check on `/status` or `/download`. There was no substrate on which
  any access control could be built. An audit sees a wrong check; it does not
  see a check that was never conceived of.
- **The product published every prompt and every generated image publicly,
  including on paid tiers**, with no notice and no opt-out. `/gallery/list`,
  `/gallery/{id}` and `/prompts/recent` were all unauthenticated. P0-D named
  "default-open security flags" and was correct, but the _data posture_ was
  default-open in a way no flag expressed.
- **No legal documents of any kind.** No terms, privacy policy, acceptable use,
  or DMCA process, for a product that hosts user-generated content and was
  about to take payments.
- **No age gate**, against provider terms that require the service not be
  "likely to be accessed by" under-18s.
- **Image keys carried no session id**, so two sessions starting in the same
  UTC second shared a gallery folder and, for the same model, silently
  overwrote each other. A live data-loss bug at ~76% likelihood per day at 500
  generates/day.

**Second divergence: the four providers were treated as an integration detail
when they are the terms of business.** Nobody read the provider terms until
"legal review", which was scheduled last as a P1 item. Reading them produced
two hard product constraints and one deploy blocker:

- Google permits its API only where the calling service is not "directed
  towards or likely to be accessed by" individuals under 18.
- Google permits **only Paid Services** where the client is made available to
  users in the EEA, Switzerland, or the UK. The app is not geo-restricted, so
  an unpaid Gemini key is a terms violation, not a privacy preference.
- Nova Canvas invisibly watermarks every image it generates.

Any of those could have changed the design. All three were discovered after
the design was built. **Read the terms of anything you resell before planning
around it.**

**Third divergence: P0-C was correctly identified as the top business blocker
and then treated as a decision when it is a measurement.** Pricing needs
measured per-generate cost. Measured cost needs a deploy. So the item the
roadmap ranked as most important could not be closed by any amount of the work
the roadmap actually scheduled. It is still open today for exactly that
reason.

**Fourth, and the one to watch for:** the roadmap's shape pulled effort toward
backend correctness because that is where an audit can see. The result is a
backend that is now substantially over-built relative to the front of the
funnel — credit ledgers, spend meters, cost meters, per-model counters, admin
endpoints, 810 backend tests — for a product with **zero users and no price**.
That work is not wasted, but the next roadmap should be suspicious of adding
more of it.

### What the last roadmap got right

Worth keeping. The P0-A diagnosis was precise and the fix was real: the
webhook resolved a user only via `metadata.userId`, and the tests hand-injected
that field, so the tests proved nothing. That is a genuinely hard class of bug
to find and the audit found it. P0-B and P0-D were also real and correctly
scoped.

## 2. Where the product actually stands

Landed and verified: webhook resolution + idempotency, cost ceilings on all
billable paths, dollar-denominated spend metering with monthly and daily
ceilings, secure-by-default flags, per-model daily caps, provider timeouts
bounded against the dispatch budget, private paid sessions with structural
enforcement, an 18+ gate, and drafted legal documents.

**Not done:** a price, a deploy, measured costs, a registered DMCA agent,
attorney review, and any part of the product that would persuade a person to
pay.

## 3. What actually stands between here and revenue

Roughly in order. Note how little of it is backend work.

**a. Deploy and measure.** Everything about cost is an estimate
(~$0.196/generate). Nothing downstream can be decided honestly until this
number is real. This is the single gating item and it is one afternoon.

**b. Decide what the free tier costs us.** Today every free generate fans out
to **all four providers**. That is the most expensive possible free tier, and
it is the unit-economics problem P0-B named but only capped rather than
restructured. The obvious question nobody has asked: should free be one or two
models and paid be all four? That single change probably moves margin more
than every ceiling and counter built so far, and it is a product decision, not
an engineering one.

**c. Set a price and an allotment.** The mechanism exists (env-configurable,
centi-credit ledger). The number does not. Needs (a), and is easier after (b).

**d. Build the conversion surface.** This is the real gap. The billing
plumbing is complete and there is nothing that would cause a person to use it:

- No pricing page content.
- No upgrade prompt at the quota wall. A user hits a limit and sees a 429.
- No credit balance shown anywhere, so nobody knows what they are spending.
- **The privacy differentiator is built but invisible.** "Your generations stay
  private" is now true for paid and is arguably the strongest upgrade argument
  the product has, and nothing in the UI says it. The public gallery does not
  say it either, and it is the one place every free user looks.

**e. Instrument the funnel, not just the spend.** We can answer "what did this
cost" and cannot answer "how many people hit the wall, and how many upgraded".
Without that, price experiments are unreadable — and the stated intent is to
experiment across price points.

**f. Publish the legal documents.** Drafts are complete but full of
`{{PLACEHOLDER}}`. Needs an entity name, jurisdiction, contact address, a
registered DMCA agent, and attorney review. Two items need a lawyer rather
than a decision: the GDPR basis for publishing free-tier content, and whether
"pay to keep your prompts private" survives scrutiny in the EEA/UK.

**g. Exercise Stripe end to end in test mode.** The webhook fixes are unit
tested against unmodified fixtures but have never seen a real Stripe event,
and the cancellation path is the one that was silently broken before.

## 4. The flywheel nobody designed on purpose

Worth naming because the next roadmap could either lean into it or break it by
accident.

Free and signed-out generations populate the public gallery. The gallery is the
landing page and the acquisition channel. Paid generations are private. So
**free users produce the corpus that attracts new users, and paying removes you
from it.** That is coherent and slightly elegant, and it happened as a
consequence of one product decision rather than by design.

Two implications: the free tier is a marketing cost with a measurable output,
which is a better way to price it than "how little can we give away"; and if
free ever becomes private too, the front page goes empty.

## 5. Decisions that need a human, not an engineer

1. Price point and monthly allotment (needs measured cost).
2. Whether the free tier keeps all four models.
3. Whether the existing public gallery corpus — generated before any notice
   existed — stays up. It ages out in 30 days on its own.
4. Entity, jurisdiction, and whether to pay for attorney review now or at
   first revenue.
5. Whether to geo-restrict the EEA/UK or just run Gemini paid. Paid is cheaper
   and better; this only becomes a question if the paid key is a problem.

## 6. Working notes on the assistant

Include these in the next plan's review strategy. They are drawn from a
documented pattern across this session, not from modesty.

**The recurring failure is fixing one instance of a class and declaring the
class closed.** Documented instances: CAPTCHA write-before-reject on
`/generate` but not `/iterate`/`/outpaint`; TTL on spend accumulators but not
IP buckets; a provider timeout for Gemini but not Nova; `buildParameterOverrides`
updated for a changed shape but not `validateConfig`; four of six legal
documents updated for tiered visibility; the unit conftest updated for the age
gate but not the E2E one; the S3 lifecycle rule not rechecked when a new prefix
was added. It shows up in _what gets checked afterwards_, not in the code
itself.

**Second: confident claims in summaries, contradicted by the assistant's own
detail.** "All four providers assign output rights" above a table saying Google
merely claims no ownership. "Everything deleted after 30 days" above a
retention table that keeps billing records. A Nova timeout described as 60s
worst case that was actually 120s. Reviewers catch these more often than they
catch code defects.

**Third, and the most dangerous: assuming an interface's shape instead of
reading it, then writing a test that mocks away the very thing that is wrong.**
`resolve_tier(event)` was called with one of three required arguments, making
every private `/status` and `/download` read a 500 — and the tests patched
`resolve_tier` with a `MagicMock` that accepted any signature. The same thing
happened on the frontend, where the age-gate modal matched on an error field
the client never populated, so the gate could never have opened.

Practical mitigations that worked: require arguments rather than defaulting
them, so a missed call site is a `TypeError`; run new tests against the
previous commit to prove they fail; and exercise the real function rather than
a mock when the call shape itself is the risk.
