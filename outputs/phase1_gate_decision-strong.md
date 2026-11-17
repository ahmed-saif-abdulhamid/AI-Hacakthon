# Phase 1 gate: evidence decision

## Outcome: STOP

> **In plain words:** People discuss this topic, but ProveIt found 1 real complaint, against the 6 it set as the bar before searching. Recommendation: don't build this as it stands.

- **Reason:** weak_pain_evidence
- **Rule fired:** rule_3
- **Next step:** -
- **Recommendation:** The topic is discussed (coverage 0.6), but verified pain signals are 1.0, below 3 and far below the pre-registered 6. Recommend: do not build this.
- **Variant researched:** 1. Late-Payment Follow-Up Toolkit
- **Pre-registered thresholds SHA-256:** `b367a0d1338c03a8f7d6318d971398eb4139dff4b5fc0ed3444023704ce5ef90`
- **Goalpost moved:** false
- **Founder decision:** overridden against the evidence (logged). Reason: Founder demo: continue as a preview to show phases 2 to 6; demand is not yet proven

Thresholds are team defaults (ASSUMPTION), registered before any source was called.

## Metrics vs thresholds

| Check | Value | Threshold | Pass |
|---|---|---|---|
| sourced_pain (weighted) | 1.0 | >= 6 | no |
| distinct_sources | 1 | >= 2 | no |
| recent_share (<= 24 months) | 0.0 | >= 0.5 | no |
| wtp_signals | 0 | >= 1 | no |
| competitors (distinct, verified) | 3 | in [1, 15] | yes |
| founder_fit (0-5, code) | 5.0 | >= 3 | yes |
| coverage | 0.6 | >= 0.5 | yes |

Claims: 14 total, 14 verified live, 0 archived matches, 0 unverified.

Code-qualified sentences not selected by the model: H1.S10.

## Advocate (case for GO)

- A freelancer reported two pending payments of $2,000 each, confirming that late payments are a real and costly problem for this audience.[C1]
- ASSUMPTION: Existing invoicing tools are described as bloated or expensive, leaving room for a lightweight, focused follow-up toolkit.
- ASSUMPTION: The founder's 7 years of freelance web development experience and skills in Google Sheets and Notion align well with building a practical, no-hype solution for fellow developers and designers.

## Skeptic (case for STOP)

- ASSUMPTION: Only one verified pain quote exists, and it describes a single anecdote rather than a recurring, quantified problem.
- Three live competitors already automate invoice reminders and integrated payments, leaving little room for a low-budget toolkit.[C3][C6][C8]
- ASSUMPTION: Founder fit is moderate (5/10) with no prior SaaS or payments experience, and the $300 budget limits credible product development.

The arguments are model-written and decide nothing; `gates.py` applies the rule precedence.

## Source coverage

| Source | Query | OK | Hits | On-topic | Covered |
|---|---|---|---|---|---|
| hn | clients pay invoices late | True | 19 | 8 | True |
| hn | chasing overdue payments | True | 17 | 13 | True |
| hn | forgot to follow up invoices | True | 20 | 1 | False |
| stackexchange | invoice reminder templates @ freelancing | True | 0 | 0 | False |
| stackexchange | clients pay invoices @ freelancing | True | 10 | 5 | True |

## Claim ledger (this variant)

| ID | Kind | Status | Weight | Cue | Quote | Source |
|---|---|---|---|---|---|---|
| C1 | pain | VERIFIED_LIVE | 1.0 | payment pending | "At that time, there were two payment pending worth $2000 each on him. I was able to do the project #1 upto the expectations agreed and send him to review back in April (but he never replied)."  | https://freelancing.stackexchange.com/questions/9768/client-feels-he-is-doing-a-favor-on-me-by-paying-invoice-because-his-requirement |
| C3 | competitor | VERIFIED_LIVE | 1.0 | - | "I'm building PayPrompt, a simple but powerful tool for freelancers and solopreneurs to automate invoice creation and payment reminders. One of the biggest struggles I hear from independent workers is late or forgotten pa..."  | https://news.ycombinator.com/item?id=43381182 |
| C6 | competitor | VERIFIED_LIVE | 1.0 | - | "Integrated Invoicing & Payments: Beyond project tracking, clients can pay invoices directly through the platform. This reduces the need for manual follow-ups or switching between tools, making it easier for freelancers t..."  | https://news.ycombinator.com/item?id=42914012 |
| C8 | competitor | VERIFIED_LIVE | 1.0 | - | "For example, when creating an invoice, the system can tell you that the client has overdue payments or that the new invoice is 40% above their usual average."  | https://news.ycombinator.com/item?id=47427522 |
| C10 | pain | verified_live (weight 0) | 0.0 | - | "It's still early, but we're testing with a small group of users who want to receive payments faster and avoid PayPal or wire fees." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=45565432 |
| C11 | pain | verified_live (weight 0) | 0.0 | - | "How to tell client I cant do any more changes till they pay invoice?" <br>off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/7724/how-to-tell-client-i-cant-do-any-more-changes-till-they-pay-invoice |
| C12 | pain | verified_live (weight 0) | 0.0 | - | "I have developed a project for a client. I am waiting for the final invoice to be settled - fixed price project." <br>label not confirmed by code | https://freelancing.stackexchange.com/questions/7724/how-to-tell-client-i-cant-do-any-more-changes-till-they-pay-invoice |
| C13 | competitor | verified_live (weight 0) | 0.0 | - | "- NudgePe, my own SaaS that chases late invoices automatically (Next.js, FastAPI, PostgreSQL, Supabase)." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=50495351 |
| C14 | pain | verified_live (weight 0) | 0.0 | - | "These are now the clauses we require in every project we do: - Payment is due X days after receipt of invoice, or immediately after the consultant has addressed any quality issues, whichever is sooner - Late payment shal..." <br>label not confirmed by code | https://news.ycombinator.com/item?id=47660815 |
| C2 | pain | verified_live (weight 0) | 0.0 | - | "I sent him the invoice yesterday after getting a confirmation from him, but he not paid yet." <br>off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/9768/client-feels-he-is-doing-a-favor-on-me-by-paying-invoice-because-his-requirement |
| C4 | pain | verified_live (weight 0) | 0.0 | - | "One of the biggest struggles I hear from independent workers is late or forgotten payments, and existing invoicing tools often feel too bloated or expensive." <br>product pitch or feature list, not a complaint | https://news.ycombinator.com/item?id=43381182 |
| C5 | pain | verified_live (weight 0) | 0.0 | - | "Why I'm here: I'd love to hear how you currently handle invoicing & payment follow-ups. - Do you use existing invoicing software, or do you track invoices manually?" <br>a question, not someone's own experience | https://news.ycombinator.com/item?id=43381182 |
| C7 | pain | verified_live (weight 0) | 0.0 | - | "This reduces the need for manual follow-ups or switching between tools, making it easier for freelancers to get paid on time." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=42914012 |
| C9 | competitor | verified_live (weight 0) | 0.0 | - | "I've been working on AirSend - we help workers to get paid in fiat currency but spend in stablecoins. Clients can pay invoices in fiat (like USD or EUR), and it's automatically converted into USDC inside your wallet (0.5..." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=45565432 |

### Sources

- [C1] https://freelancing.stackexchange.com/questions/9768/client-feels-he-is-doing-a-favor-on-me-by-paying-invoice-because-his-requirement (verified_live, weight 1.0)
- [C3] https://news.ycombinator.com/item?id=43381182 (verified_live, weight 1.0)
- [C6] https://news.ycombinator.com/item?id=42914012 (verified_live, weight 1.0)
- [C8] https://news.ycombinator.com/item?id=47427522 (verified_live, weight 1.0)
