# Phase 1 gate: evidence decision

## Outcome: STOP

> **In plain words:** People discuss this topic, but ProveIt found 3 real complaints, against the 6 it set as the bar before searching. Recommendation: don't build this as it stands.

- **Reason:** checks_failed
- **Rule fired:** rule_7
- **Next step:** -
- **Recommendation:** Failed: sourced_pain, distinct_sources, wtp_signals. Recommend: stop. (STOP for variant 1; the other angles were scored but not researched.)
- **Variant researched:** 1. Late-Payment Follow-Up Toolkit
- **Pre-registered thresholds SHA-256:** `123b85bcf0e37ce958ab6d76fd569f17ebdf0ad55803378ace5b75c8d5826dec`
- **Goalpost moved:** false
- **Founder decision:** overridden against the evidence (logged). Reason: I want to preview the landing page, product build, and store flow for freelancers I know.

Thresholds are team defaults (ASSUMPTION), registered before any source was called.

## Metrics vs thresholds

| Check | Value | Threshold | Pass |
|---|---|---|---|
| sourced_pain (weighted) | 3.0 | >= 6 | no |
| distinct_sources | 1 | >= 2 | no |
| recent_share (<= 24 months) | 1.0 | >= 0.5 | yes |
| wtp_signals | 0 | >= 1 | no |
| competitors (distinct, verified) | 6 | in [1, 15] | yes |
| founder_fit (0-5, code) | 5.0 | >= 3 | yes |
| coverage | 0.6 | >= 0.5 | yes |

Claims: 16 total, 16 verified live, 0 archived matches, 0 unverified.

## Advocate (case for GO)

- Freelancers report an average 23-day payment delay, confirming a real and costly late-payment problem.[C6]
- ASSUMPTION: Multiple live competitors already offer automated reminders, integrated invoicing, and late-payment clauses, proving market demand.
- ASSUMPTION: The founder's 7 years of freelance web development experience and low-budget, no-hype approach align well with building a practical follow-up toolkit.

## Skeptic (case for STOP)

- ASSUMPTION: Only one distinct source backs the pain claims, and zero willingness-to-pay signals exist, making demand unproven.
- Six live competitors already automate reminders, embed payment links, and flag overdue clients, leaving little room for a new toolkit.[C2]
- ASSUMPTION: Founder fit is moderate (5/10) with no prior payments or SaaS experience, and the $300 budget limits reach in a crowded market.

The arguments are model-written and decide nothing; `gates.py` applies the rule precedence.

## Source coverage

| Source | Query | OK | Hits | On-topic | Covered |
|---|---|---|---|---|---|
| hn | clients pay invoices late | True | 19 | 14 | True |
| hn | chasing overdue payments | True | 17 | 16 | True |
| hn | forgot to send reminder | True | 19 | 14 | True |
| stackexchange | invoice reminder templates @ freelancing | True | 0 | 0 | False |
| stackexchange | clients pay invoices @ freelancing | False | 0 | 0 | False | Client error '400 Bad Request' for url 'https://api.stackexc

## Claim ledger (this variant)

| ID | Kind | Status | Weight | Cue | Quote | Source |
|---|---|---|---|---|---|---|
| C11 | competitor | VERIFIED_LIVE | 1.0 | - | "- NudgePe, my own SaaS that chases late invoices automatically (Next.js, FastAPI, PostgreSQL, Supabase)."  | https://news.ycombinator.com/item?id=50495351 |
| C14 | pain | VERIFIED_LIVE | 1.0 | pays late | "That's why a contract is so important: it describes what happens when a client pays late, and presumably sets terms to either make it worthwhile for the worker, or gives the worker an easy way out of the contract."  | https://news.ycombinator.com/item?id=43640766 |
| C15 | competitor | VERIFIED_LIVE | 1.0 | - | "For example, when creating an invoice, the system can tell you that the client has overdue payments or that the new invoice is 40% above their usual average."  | https://news.ycombinator.com/item?id=47427522 |
| C16 | pain | VERIFIED_LIVE | 1.0 | never pay | "Good thing I never pay my late AWS payments!"  | https://news.ycombinator.com/item?id=50516876 |
| C2 | competitor | VERIFIED_LIVE | 1.0 | - | "- Automated, non-intrusive reminders that follow up with clients for overdue payments."  | https://news.ycombinator.com/item?id=43381182 |
| C4 | competitor | VERIFIED_LIVE | 1.0 | - | "Integrated Invoicing & Payments: Beyond project tracking, clients can pay invoices directly through the platform. This reduces the need for manual follow-ups or switching between tools, making it easier for freelancers t..."  | https://news.ycombinator.com/item?id=42914012 |
| C6 | pain | VERIFIED_LIVE | 1.0 | late payment | "We're in a particularly credit poor industry but our average delay due to late payment is 23 days."  | https://news.ycombinator.com/item?id=47660815 |
| C7 | competitor | VERIFIED_LIVE | 1.0 | - | "These are now the clauses we require in every project we do: - Payment is due X days after receipt of invoice, or immediately after the consultant has addressed any quality issues, whichever is sooner - Late payment shal..."  | https://news.ycombinator.com/item?id=47660815 |
| C8 | competitor | VERIFIED_LIVE | 1.0 | - | "I've been working on AirSend - we help workers to get paid in fiat currency but spend in stablecoins. Clients can pay invoices in fiat (like USD or EUR), and it's automatically converted into USDC inside your wallet (0.5..."  | https://news.ycombinator.com/item?id=45565432 |
| C1 | pain | verified_live (weight 0) | 0.0 | - | "One of the biggest struggles I hear from independent workers is late or forgotten payments, and existing invoicing tools often feel too bloated or expensive." <br>product pitch or feature list, not a complaint | https://news.ycombinator.com/item?id=43381182 |
| C10 | pain | verified_live (weight 0) | 0.0 | - | "- How often do you deal with late payments or awkward follow-ups?" <br>product pitch or feature list, not a complaint | https://news.ycombinator.com/item?id=43381182 |
| C12 | pain | verified_live (weight 0) | 0.0 | - | "I forgot to send the invoice." <br>label not confirmed by code | https://news.ycombinator.com/item?id=48662338 |
| C13 | pain | verified_live (weight 0) | 0.0 | - | "Most clients aren't looking to screw you in advance; they just want the work done, but don't always have the money in time to pay for it (true, sometimes as a result of their own failings)." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=43640766 |
| C3 | pain | verified_live (weight 0) | 0.0 | manual | "This reduces the need for manual follow-ups or switching between tools, making it easier for freelancers to get paid on time." <br>general wording, not someone's own complaint | https://news.ycombinator.com/item?id=42914012 |
| C5 | pain | verified_live (weight 0) | 0.0 | - | "Ironically, the good clients pay within 2-3 days normally, and the difficult ones are very "long tail"." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=47660815 |
| C9 | pain | verified_live (weight 0) | 0.0 | - | "It's still early, but we're testing with a small group of users who want to receive payments faster and avoid PayPal or wire fees." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=45565432 |

### Sources

- [C6] https://news.ycombinator.com/item?id=47660815 (verified_live, weight 1.0)
- [C2] https://news.ycombinator.com/item?id=43381182 (verified_live, weight 1.0)
