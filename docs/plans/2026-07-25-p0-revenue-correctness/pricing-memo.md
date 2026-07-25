# P0-C — Pricing decision

**Status: DECIDED 2026-07-25.** Supersedes the options memo. Numbers below are
starting points chosen for experimentation, not commitments — every one is an
env var (see "Configuration" below).

## Decisions

| Question                | Decision                                                                    |
| ----------------------- | --------------------------------------------------------------------------- |
| Billing structure       | **Subscription + hard credit allotment + metered overage**                  |
| Margin target           | **30–35% worst case** (not 60% — a 60% floor priced the product out)        |
| Free tier model access  | **All 4 models**                                                            |
| Fan-out as a tier lever | **Rejected** — free gets all 4, so model access can't be an upgrade trigger |
| Price experimentation   | **Env vars, served to the UI from the backend**                             |

## Launch numbers (starting points)

| Plan   | Price  | Credits/mo | Worst-case COGS | Worst-case margin    |
| ------ | ------ | ---------- | --------------- | -------------------- |
| Free   | $0     | 5          | $1.00           | — (acquisition cost) |
| Pro    | $19/mo | 65         | $13.00          | 32%                  |
| Studio | $49/mo | 170        | $34.00          | 31%                  |

- Generate = **1.00 credit** (~$0.20 COGS)
- Refine / Outpaint = **0.25 credit** (~$0.05 COGS)
- Overage = **$0.50/credit** (60% margin)

Worst case assumes 100% allotment redemption. At the ~60% redemption typical of
metered SaaS, realized margin lands ~55–60%. The 30–35% floor is the number to
_design_ against; it is not the expected outcome.

Refine is deliberately cheap at 0.25 credit. Cross-model conversational
iteration is the genuine engineering wedge — pricing should push users into it,
not ration it.

## The free tier is now the largest exposure — and it is a budget, not a rate limit

"Free tier all 4 models" is the right call for the first-run experience, but it
changes what the free tier _is_.

Today, free is a **rolling 1-hour rate limit**: `config.py:98-100`
(`free_generate_limit=1`, `free_window_seconds=3600`) with the window reset by
`repository.py:68-96`. That permits 24 generates/day ≈ **720/month**. At all-4
pricing that is **~$144/month of COGS per free user**, unbounded in aggregate.

A rate limit does not bound monthly spend. **The free tier must become a monthly
credit allotment** (`FREE_MONTHLY_CREDITS`, default 5), replacing the hourly
window entirely. This is a required change in `users/quota.py`, folded into
Sprint 1 Track B.

Aggregate free-tier spend needs its own line on the admin dashboard and its own
alarm. At 10,000 free users × 5 credits it is $10k/month — a real budget line,
not a rounding error, and the number most likely to move when you experiment.

## Configuration — everything is an env var

Costs and credits are stored as **integers** (micro-dollars, centi-credits).
Never floats: these feed DynamoDB atomic counters.

```bash
# --- COGS table: what a provider call costs US (micro-dollars) ---
# Seeded with list-price estimates; corrected from real invoices once the meter runs.
COST_GEMINI_GENERATE_USD_MICROS=39000
COST_NOVA_GENERATE_USD_MICROS=40000
COST_OPENAI_GENERATE_USD_MICROS=40000
COST_FIREFLY_GENERATE_USD_MICROS=70000
COST_<MODEL>_REFINE_USD_MICROS=...      # per model, per operation
COST_<MODEL>_OUTPAINT_USD_MICROS=...
COST_ENHANCE_USD_MICROS=7000            # gpt-4o adaptation

# --- Credit pricing: what an action costs the USER (centi-credits) ---
CREDITS_PER_GENERATE=100                # 1.00 credit
CREDITS_PER_REFINE=25                   # 0.25 credit
CREDITS_PER_OUTPAINT=25
CREDITS_PER_ENHANCE=0

# --- Tier allotments (centi-credits per period) ---
FREE_MONTHLY_CREDITS=500                # 5 credits
PRO_MONTHLY_CREDITS=6500                # 65 credits
STUDIO_MONTHLY_CREDITS=17000            # 170 credits
# Free accounts only. PAID allotments reset on Stripe's subscription period
# boundaries (current_period_start/end), never on a fixed clock — see below.
FREE_CREDIT_PERIOD_SECONDS=2592000      # 30 days

# --- Display price + Stripe wiring ---
PRO_PRICE_USD_CENTS=1900
STUDIO_PRICE_USD_CENTS=4900
OVERAGE_USD_CENTS_PER_CREDIT=50
STRIPE_PRICE_ID_PRO=price_xxx
STRIPE_PRICE_ID_STUDIO=price_xxx

# --- Spend ceilings (dollars, the backstop) ---
GLOBAL_DAILY_SPEND_CEILING_USD_CENTS=...
FREE_TIER_DAILY_SPEND_CEILING_USD_CENTS=...
```

### Paid credits reset on Stripe's period, not a fixed 30 days

Stripe's monthly billing cycles run 28–31 days. A fixed 30-day credit window
drifts against them, so a subscriber gets a fresh allotment before they are
billed in some months and goes short after renewal in others — both of which
are support tickets, and the second is a refund request.

Persist `current_period_start` / `current_period_end` from the subscription
webhook and reset paid allotments against those boundaries. Only free accounts,
which have no Stripe period, use a fixed cycle.

### Serve pricing from the backend, not `VITE_` vars

If the UI reads prices from `VITE_*` build-time vars, every price experiment
requires a frontend rebuild and redeploy — which is enough friction to stop the
experimentation actually happening.

Instead add a public **`GET /pricing`** endpoint returning tier names, prices,
credit allotments, and per-action credit costs from Lambda env. `UpgradeModal.tsx`
renders whatever it returns. One env change then flips backend enforcement and
UI display together, with no rebuild.

This also removes a whole class of bug: the UI cannot advertise a price that
disagrees with what the backend enforces, because there is one source.

## Before any price goes public

Every margin figure above rests on an **estimated** ~$0.20/generate taken from
public rate cards. Firefly is credit-based and the least certain of the four
(estimated $0.05–0.10 — a 2× range). If the real number is at the top of that
range, Pro's worst-case margin drops from 32% to ~24%.

**Do not commit to public prices until the P0-B meter has run against real
traffic and the COGS table holds measured numbers.** The whole point of putting
the table in env vars is that correcting it is a config change, not a code change.

## Open, not blocking

- **Team / per-seat tier.** Pooled credits across seats; redemption drops
  sharply with team size, so margin lands ~70–75% — the best of any option, and
  the tier where per-user model-preference data ("Firefly wins for YOUR
  prompts") becomes a moat rather than a feature. Needs org/seat management that
  doesn't exist. Revisit post-launch; the credit mechanism built now is the same
  one it needs.
- **Credit expiry / rollover.** Unspecified. Default assumption: allotment does
  not roll over. Worth deciding before launch since it affects redemption rate,
  which is what the margin projection rests on.
