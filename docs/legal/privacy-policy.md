# Privacy Policy

**DRAFT — requires attorney review before publication.** Placeholders in
`{{BRACES}}` must be filled by the operator.

**Last updated:** {{DATE}}

## The short version

- **Your prompts and generated images are published publicly.** Every one, on
  every tier. There is no opt-out today.
- Your prompts and images are sent to Google, Amazon, OpenAI, and Adobe.
- {{GEMINI_TIER_STATEMENT}} — see "Third-party AI providers" below.
- We do not sell your personal information.
- Everything is deleted after 30 days.

## What we collect

**Prompts and images you submit.** The text you type and any image you upload
or that the Service generates on your behalf.

**Account information**, if you sign in: your email address and a user
identifier, held in Amazon Cognito. If you do not sign in, we do not have your
email.

**Usage and quota records.** Counts of generations and refinements, which model
you chose to refine, and timestamps. Stored in DynamoDB and used to enforce
quotas and to understand which models people prefer.

**A hashed form of your IP address.** When you use the Service without an
account, we hash your IP address and use the hash as a quota key. We store the
hash, not the address.

**Billing information**, if you subscribe: a Stripe customer identifier and
subscription status. **Card details go directly to Stripe and never reach our
servers.**

**Logs.** Request metadata and errors, retained for 30 days in CloudWatch.

## What is public

**Everything you generate is published.** Specifically:

- Generated images appear in a **public gallery** readable by anyone, including
  people who are not signed in and are not our users.
- Prompt text appears in a **public feed of recent prompts**, also readable by
  anyone.

This is the default and current behaviour for every tier, including paid tiers,
and there is no setting to change it.

**Prompts are free text and we do not scan them for personal information before
publishing.** If you type your name, someone else's name, an address, an
employer, a medical detail, or a confidential idea into a prompt, it is
published. Please do not.

To have specific content removed, email {{CONTACT_EMAIL}}. We will remove it
within {{N}} days. Cached copies, including in CloudFront, may persist for a
period after removal.

## Third-party AI providers

Your prompt, and any source image, is transmitted to the providers you generate
with:

| Provider                              | Receives             | Their terms                                                |
| ------------------------------------- | -------------------- | ---------------------------------------------------------- |
| Google (Gemini)                       | Prompt, source image | [Gemini API terms](https://ai.google.dev/gemini-api/terms) |
| Amazon (Nova Canvas, via AWS Bedrock) | Prompt, source image | [AWS Service Terms](https://aws.amazon.com/service-terms/) |
| OpenAI (DALL-E 3, gpt-image-1)        | Prompt, source image | [OpenAI terms](https://openai.com/policies/service-terms/) |
| Adobe (Firefly)                       | Prompt, source image | [Adobe terms](https://www.adobe.com/legal/terms.html)      |

We also use one provider for the optional prompt-enhancement feature. If you
use it, your prompt goes to that provider as well.

**Google Gemini specifically.** Google's terms distinguish paid from unpaid API
use. On the **unpaid** tier, Google states that it uses submitted content and
generated responses to improve Google products, and that human reviewers may
read them. On the **paid** tier, Google states that it does not use prompts or
responses to improve its products.

{{GEMINI_TIER_STATEMENT}}

> Operator: replace this with one of the following, whichever is true of the
> production key. This is not detectable from the code and must be confirmed
> against the key's billing status.
>
> - "We use the paid tier. Google does not use your prompts or the resulting
>   images to improve its products."
> - "We use the unpaid tier. This means Google uses your prompts and the
>   resulting images to improve Google products, and Google states that human
>   reviewers may read them."

## Why we process it

| Purpose                                          | Basis (GDPR)              |
| ------------------------------------------------ | ------------------------- |
| Generating images you asked for                  | Performance of a contract |
| Enforcing quotas and preventing abuse            | Legitimate interests      |
| Billing and subscription management              | Performance of a contract |
| Publishing to the public gallery and prompt feed | {{BASIS}} — see note      |
| Security and fraud prevention                    | Legitimate interests      |
| Complying with legal obligations                 | Legal obligation          |

> Note for review: publication is currently unavoidable and bundled into use of
> the Service, which makes consent difficult to characterise as freely given.
> Counsel should advise whether this is defensible as contractual necessity or
> whether an opt-out is required. This is the strongest argument for making
> publication opt-in.

## How long we keep it

- Generated images and session data: **30 days**, then deleted automatically by
  an S3 lifecycle rule.
- Logs: 30 days.
- Quota and usage counters: rolling windows, with automatic expiry.
- Guest records: expire automatically.
- Account and billing records: for as long as you have an account, plus any
  period required for tax and accounting purposes.

## Cookies

We use a signed cookie to identify guest sessions for quota purposes. If you
sign in, standard authentication tokens are used. We do not use advertising or
cross-site tracking cookies.

If CAPTCHA is enabled, Cloudflare Turnstile is used and sets its own cookies
under [Cloudflare's privacy policy](https://www.cloudflare.com/privacypolicy/).

## Your rights

Depending on where you live you may have the right to access, correct, delete,
export, or restrict processing of your personal data, and to object to
processing based on legitimate interests. California residents have rights
under the CCPA/CPRA, including the right to know and the right to delete.

**We do not sell personal information and do not share it for cross-context
behavioural advertising.**

To exercise any of these, email {{CONTACT_EMAIL}}. We will respond within the
period required by applicable law.

Note that because generated content is deleted after 30 days, most data about
you ages out on its own.

## Age

**The Service is for adults aged 18 and over.** We do not knowingly collect
personal information from anyone under 18. If you believe a person under 18 has
used the Service, contact {{CONTACT_EMAIL}} and we will delete the data.

## International transfers

We operate in AWS {{REGION}}. Our providers process data in the United States
and potentially elsewhere. If you are in the EEA or UK, your data is
transferred outside your region under {{TRANSFER_MECHANISM}}.

## Security

Data is encrypted in transit and at rest in AWS. Access is limited by IAM.
Payment details never reach our systems. No system is perfectly secure, and we
cannot guarantee absolute security.

## Changes

We will post material changes here and, where required, notify you before they
take effect.

## Contact

{{CONTACT_EMAIL}}. {{EU_REPRESENTATIVE_IF_REQUIRED}}
