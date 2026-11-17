# Phase 1 gate: evidence decision

## Outcome: STOP

- **Reason:** checks_failed
- **Rule fired:** rule_7
- **Next step:** -
- **Recommendation:** Failed: sourced_pain. Recommend: stop.
- **Variant researched:** 1. Late Payment Follow-Up Toolkit
- **Pre-registered thresholds SHA-256:** `b367a0d1338c03a8f7d6318d971398eb4139dff4b5fc0ed3444023704ce5ef90`
- **Goalpost moved:** false
- **Founder decision:** overridden against the evidence (logged). Reason: Preview Phases 2-6 for the demo; the weak pain evidence is accepted as a known risk and demand is not proven

Thresholds are team defaults (ASSUMPTION), registered before any source was called.

## Metrics vs thresholds

| Check | Value | Threshold | Pass |
|---|---|---|---|
| sourced_pain (weighted) | 3.0 | >= 6 | no |
| distinct_sources | 2 | >= 2 | yes |
| recent_share (<= 24 months) | 0.5 | >= 0.5 | yes |
| wtp_signals | 1 | >= 1 | yes |
| competitors (distinct, verified) | 1 | in [1, 15] | yes |
| founder_fit (0-5, code) | 5.0 | >= 3 | yes |
| coverage | 1.0 | >= 0.5 | yes |

Claims: 27 total, 10 verified live, 17 archived matches, 0 unverified.

Code-qualified sentences not selected by the model: H47.S2.

## Advocate (case for GO)

- ASSUMPTION: Late payments happen regularly, with at least one client monthly (C73).
- ASSUMPTION: Freelancers dislike sending follow-ups due to emotional discomfort (C74).
- ASSUMPTION: A gap exists where freelancers rely on Payoneer despite better alternatives (C92).

## Skeptic (case for STOP)

- ASSUMPTION: Missing evidence: No verified claim shows late payments cause financial loss or operational harm beyond emotional frustration.
- ASSUMPTION: Weak wtp signal: Only one wtp claim (C88) exists, and it's about PayPal charges, not payment automation or AI tools.
- ASSUMPTION: Crowded competition: Competitor C94 describes a full suite of financial tools, suggesting market saturation with similar offerings.

The arguments are model-written and decide nothing; `gates.py` applies the rule precedence.

## Source coverage

| Source | Query | OK | Hits | On-topic | Covered |
|---|---|---|---|---|---|
| hn | payment follow up mess | True | 20 | 4 | True |
| hn | late payments never come | True | 20 | 6 | True |
| hn | chasing clients for payment | True | 20 | 11 | True |
| hn | freelance developers | True | 20 | 20 | True |
| stackexchange | invoice follow up @ freelancing | True | 3 | 3 | True |
| stackexchange | payment follow @ freelancing | True | 10 | 10 | True |

## Claim ledger (this variant)

| ID | Kind | Status | Weight | Cue | Quote | Source |
|---|---|---|---|---|---|---|
| C73 | pain | VERIFIED_LIVE | 1.0 | does not pay | "Each month there is at least one client who does not pay my invoice."  | https://news.ycombinator.com/item?id=45537969 |
| C74 | pain | VERIFIED_LIVE | 1.0 | despise | "I absolutely despise sending follow up reminders it feels needy, awkward, and just a reframing of mental energy."  | https://news.ycombinator.com/item?id=45537969 |
| C92 | competitor | VERIFIED_LIVE | 1.0 | - | "After speaking with 50+ freelancers, we saw a clear gap: despite issues like high fees and account freezes, many still rely on Payoneer because no alternative offers the same experience."  | https://news.ycombinator.com/item?id=48012653 |
| C94 | competitor | VERIFIED_LIVE | 1.0 | - | "What we're building: - Virtual USD accounts - Payment links for clients - Virtual cards - P2P transfers - Access to global stocks & ETFs We're still early, but the waitlist is live."  | https://news.ycombinator.com/item?id=48012653 |
| C71 | pain | ARCHIVED_MATCH | 0.5 | doesn't help | "Invoicing and sometimes needing to follow up on late payments doesn't help either." <br>page unreachable; archived match | https://freelancing.stackexchange.com/questions/2621/away-from-hourly-work-to-a-prepaid-package-of-hours |
| C72 | pain | ARCHIVED_MATCH | 0.5 | waste | "There's more time wasted than I care for, and the late payments are especially infuriating." <br>page unreachable; archived match | https://freelancing.stackexchange.com/questions/2621/away-from-hourly-work-to-a-prepaid-package-of-hours |
| C88 | wtp | ARCHIVED_MATCH | 0.5 | charge | "The payment will be made via PayPal, and he is willing to cover the payment gateway charges of PayPal." <br>page unreachable; archived match | https://freelancing.stackexchange.com/questions/10519/how-to-mention-payment-gateway-charges-in-an-invoice |
| C75 | wtp | verified_live (weight 0) | 0.0 | - | "Connect to Stripe or PayPal, it predicts who will likely pay late and automatically sends out a reminder email that gets firmer each time." <br>label not confirmed by code | https://news.ycombinator.com/item?id=45537969 |
| C76 | pain | archived_match (weight 0) | 0.0 | - | "My frustrations have grown out of their complete lack of trust in my skill and ability; they push past my recommendations for what their friends "vote" on, despite any facts, studies, "proof," etc. I send to justify my c..." <br>page unreachable; archived match; off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/935/firing-a-client-due-to-difficult-ongoing-work-relationship |
| C77 | pain | archived_match (weight 0) | 0.0 | - | "As if that wasn't enough, their emails have become increasingly harsh in tone - even to the extent where they send follow up emails to apologize a day or so later." <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/935/firing-a-client-due-to-difficult-ongoing-work-relationship |
| C78 | wtp | verified_live (weight 0) | 0.0 | - | "So, I am thinking...what if an AI tool could send those reminders for me?" <br>label not confirmed by code | https://news.ycombinator.com/item?id=45537969 |
| C79 | pain | archived_match (weight 0) | 0.0 | - | "To date I've been supplying an invoice for the total amount , with follow up statements for each payment." <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/2759/what-is-the-correct-way-to-handle-progressive-billing-especially-in-the-uk |
| C80 | pain | archived_match (weight 0) | 0.0 | - | "If we take 'correct' to loosely mean "I'm not going to end up with a convoluted tax return at the end of the year", is this the 'correct' way, or should I be issuing a separate invoice for each payment?" <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/2759/what-is-the-correct-way-to-handle-progressive-billing-especially-in-the-uk |
| C81 | pain | archived_match (weight 0) | 0.0 | - | "Follow up questions: what is the proper format for handling these types of payments?" <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/2759/what-is-the-correct-way-to-handle-progressive-billing-especially-in-the-uk |
| C82 | pain | archived_match (weight 0) | 0.0 | - | "My contract doesn't contain a kill clause, so I assume that I don't have legal standing to demand 90% payment." <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/8198/contract-canceled-after-90-of-effort-was-expended-client-pegs-delivered-value |
| C83 | pain | archived_match (weight 0) | 0.0 | - | "Since they appear to be committed to their position, I expect that if I invoice them for 90% of the contract value, they will only pay 50%." <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/8198/contract-canceled-after-90-of-effort-was-expended-client-pegs-delivered-value |
| C84 | wtp | archived_match (weight 0) | 0.0 | - | "I've explained that I will have to submit an invoice for 90% because I've already expended 90% of the effort required to complete the project, but that they may of course still request completion of the full project unde..." <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/8198/contract-canceled-after-90-of-effort-was-expended-client-pegs-delivered-value |
| C85 | pain | archived_match (weight 0) | 0.0 | - | "Then he immediately cut me off without paying me the payment for the other 1/2 month." <br>page unreachable; archived match; off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/9779/international-employer-initiated-paypal-buyer-claim-without-any-reason |
| C86 | pain | archived_match (weight 0) | 0.0 | - | "I worked for this employer for a month, and he only paid me for half-month then suddenly replaced me after I delivered the MVP." <br>page unreachable; archived match; off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/9779/international-employer-initiated-paypal-buyer-claim-without-any-reason |
| C87 | wtp | archived_match (weight 0) | 0.0 | - | "Actions I'm planning to do: Go public on this and be vocal about everything to warn other freelancers Make the product open source." <br>page unreachable; archived match; off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/9779/international-employer-initiated-paypal-buyer-claim-without-any-reason |
| C89 | pain | archived_match (weight 0) | 0.0 | - | "So when I make the invoice, how shall I write the entry of the payment gateway charges in the invoice?" <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/10519/how-to-mention-payment-gateway-charges-in-an-invoice |
| C90 | pain | archived_match (weight 0) | 0.0 | - | "Things like: Remember to follow up Organize tax documents/forms Reply to a client Send invoice Keeping track of feedback and requirements The thing with freelancing is that clients contact at scattered times throughout t..." <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/10646/just-thinking-about-clients-and-things-to-do-create-anxiety |
| C91 | pain | archived_match (weight 0) | 0.0 | - | "Things like: Remember to follow up Organize tax documents/forms Reply to a client Send invoice Keeping track of feedback and requirements The thing with freelancing is that clients contact at scattered times throughout t..." <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/10646/just-thinking-about-clients-and-things-to-do-create-anxiety |
| C93 | trend | verified_live (weight 0) | 0.0 | - | "Existing solutions focus a lot on USD accounts but we want to go a step further and offer invoice tooling and getting the details right for freelancers." <br>context only; never counted by a gate | https://news.ycombinator.com/item?id=48012653 |
| C95 | pain | verified_live (weight 0) | 0.0 | - | "I was tracking billable hours using Google Forms (yes, really). Every time I switched tasks, I had to manually fill out the project name, start time, end time, and description." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=46346549 |
| C96 | pain | verified_live (weight 0) | 0.0 | - | "After forgetting to log hours several times and losing money, I decided there had to be a better way." <br>label not confirmed by code | https://news.ycombinator.com/item?id=46346549 |
| C97 | competitor | verified_live (weight 0) | 0.0 | - | "tmpo is a CLI time tracker that gets out of your way: - Automatically detects project names from git repos or ." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=46346549 |

### Sources

No statement in this file carries a verified citation; every claim above is labelled ASSUMPTION.
