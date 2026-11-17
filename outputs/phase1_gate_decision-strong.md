# Phase 1 gate: evidence decision

## Outcome: STOP

> **In plain words:** People discuss this topic, but ProveIt found 2 real complaints, against the 6 it set as the bar before searching. Recommendation: don't build this as it stands.

- **Reason:** weak_pain_evidence
- **Rule fired:** rule_3
- **Next step:** -
- **Recommendation:** The topic is discussed (coverage 0.8), but verified pain signals are 2.0, below 3 and far below the pre-registered 6. Recommend: do not build this.
- **Variant researched:** 1. Late-Payment Follow-Up Toolkit
- **Pre-registered thresholds SHA-256:** `b367a0d1338c03a8f7d6318d971398eb4139dff4b5fc0ed3444023704ce5ef90`
- **Goalpost moved:** false
- **Founder decision:** overridden against the evidence (logged). Reason: Founder demo: continue as a preview to show phases 2 to 6; demand is not yet proven

Thresholds are team defaults (ASSUMPTION), registered before any source was called.

## Metrics vs thresholds

| Check | Value | Threshold | Pass |
|---|---|---|---|
| sourced_pain (weighted) | 2.0 | >= 6 | no |
| distinct_sources | 1 | >= 2 | no |
| recent_share (<= 24 months) | 1.0 | >= 0.5 | yes |
| wtp_signals | 0 | >= 1 | no |
| competitors (distinct, verified) | 5 | in [1, 15] | yes |
| founder_fit (0-5, code) | 5.0 | >= 3 | yes |
| coverage | 0.8 | >= 0.5 | yes |

Claims: 19 total, 19 verified live, 0 archived matches, 0 unverified.

Code-qualified sentences not selected by the model: H1.S10.

## Advocate (case for GO)

- Freelancers consistently report late payments as a major struggle and existing invoicing tools as too bloated or expensive.[C7]
- There is clear demand for simple, automated payment follow-ups that avoid full accounting suites.[C8][C11]
- Multiple competitors are already building automated reminder and invoicing features, validating the problem space.[C6]

## Skeptic (case for STOP)

- ASSUMPTION: Only one distinct source backs the pain, and zero willingness-to-pay signals suggest demand is unproven.
- Five live competitors already automate reminders and invoicing, leaving little room for a new toolkit.[C6]
- ASSUMPTION: Founder fit is moderate but the $300 budget and 10 hrs/week constrain building a differentiated product.

The arguments are model-written and decide nothing; `gates.py` applies the rule precedence.

## Source coverage

| Source | Query | OK | Hits | On-topic | Covered |
|---|---|---|---|---|---|
| hn | clients pay invoices late | True | 20 | 8 | True |
| hn | chasing overdue payments | True | 20 | 16 | True |
| hn | forgot to send reminder | True | 20 | 13 | True |
| stackexchange | invoice reminder templates @ freelancing | True | 0 | 0 | False |
| stackexchange | clients pay invoices @ freelancing | True | 10 | 5 | True |

## Claim ledger (this variant)

| ID | Kind | Status | Weight | Cue | Quote | Source |
|---|---|---|---|---|---|---|
| C10 | pain | VERIFIED_LIVE | 1.0 | lose time | "The idea came from repeatedly watching freelancers (and honestly, myself) lose time to admin just to get paid. Most tools I tried felt like full accounting suites when all I really wanted was: • create an invoice quickly..."  | https://news.ycombinator.com/item?id=46771990 |
| C11 | pain | VERIFIED_LIVE | 1.0 | overdue | "Most tools I tried felt like full accounting suites when all I really wanted was: • create an invoice quickly • send it • see what's paid / overdue • and automatically chase unpaid ones So I built Experi to focus only on..."  | https://news.ycombinator.com/item?id=46771990 |
| C12 | competitor | VERIFIED_LIVE | 1.0 | - | "It currently supports: • fast invoice creation • client and project management • scheduled and recurring invoices • automatic chasing of overdue invoices • clear tracking of paid vs outstanding The goal is not to replace..."  | https://news.ycombinator.com/item?id=46771990 |
| C18 | competitor | VERIFIED_LIVE | 1.0 | - | "For example, when creating an invoice, the system can tell you that the client has overdue payments or that the new invoice is 40% above their usual average."  | https://news.ycombinator.com/item?id=47427522 |
| C3 | competitor | VERIFIED_LIVE | 1.0 | - | "Integrated Invoicing & Payments: Beyond project tracking, clients can pay invoices directly through the platform. This reduces the need for manual follow-ups or switching between tools, making it easier for freelancers t..."  | https://news.ycombinator.com/item?id=42914012 |
| C5 | competitor | VERIFIED_LIVE | 1.0 | - | "Bills can change, Splitify tracks costs each billing cycle using your bank account and then sends out a request with latest amount via email AND text. Plus it sends reminders until you get paid."  | https://news.ycombinator.com/item?id=45431193 |
| C6 | competitor | VERIFIED_LIVE | 1.0 | - | "I'm building PayPrompt, a simple but powerful tool for freelancers and solopreneurs to automate invoice creation and payment reminders. One of the biggest struggles I hear from independent workers is late or forgotten pa..."  | https://news.ycombinator.com/item?id=43381182 |
| C7 | pain | VERIFIED_LIVE | 1.0 | struggl | "One of the biggest struggles I hear from independent workers is late or forgotten payments, and existing invoicing tools often feel too bloated or expensive."  | https://news.ycombinator.com/item?id=43381182 |
| C8 | pain | VERIFIED_LIVE | 1.0 | overdue | "- Automated, non-intrusive reminders that follow up with clients for overdue payments."  | https://news.ycombinator.com/item?id=43381182 |
| C9 | pain | VERIFIED_LIVE | 1.0 | manually | "Why I'm here: I'd love to hear how you currently handle invoicing & payment follow-ups. - Do you use existing invoicing software, or do you track invoices manually?"  | https://news.ycombinator.com/item?id=43381182 |
| C1 | pain | verified_live (weight 0) | 0.0 | - | "At that time, there were two payment pending worth $2000 each on him. I was able to do the project #1 upto the expectations agreed and send him to review back in April (but he never replied)." <br>label not confirmed by code | https://freelancing.stackexchange.com/questions/9768/client-feels-he-is-doing-a-favor-on-me-by-paying-invoice-because-his-requirement |
| C13 | pain | verified_live (weight 0) | 0.0 | - | "How to tell client I cant do any more changes till they pay invoice? I am new to freelancing. I have developed a project for a client." <br>label not confirmed by code | https://freelancing.stackexchange.com/questions/7724/how-to-tell-client-i-cant-do-any-more-changes-till-they-pay-invoice |
| C14 | pain | verified_live (weight 0) | 0.0 | - | "I'm unsure how to phrase or communicate that I cannot do anymore change till my previous invoice has been paid." <br>off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/7724/how-to-tell-client-i-cant-do-any-more-changes-till-they-pay-invoice |
| C15 | pain | verified_live (weight 0) | 0.0 | - | "These are now the clauses we require in every project we do: - Payment is due X days after receipt of invoice, or immediately after the consultant has addressed any quality issues, whichever is sooner - Late payment shal..." <br>label not confirmed by code | https://news.ycombinator.com/item?id=47660815 |
| C16 | pain | verified_live (weight 0) | 0.0 | - | "- In the event of a late payment the invoice for the next deliverable shall immediately fall due. - The consultant shall be entitled to shift deadlines on deliverables in the event of a late payment as a result of any wo..." <br>label not confirmed by code | https://news.ycombinator.com/item?id=47660815 |
| C17 | pain | verified_live (weight 0) | 0.0 | - | "- The consultant shall be entitled to shift deadlines on deliverables in the event of a late payment as a result of any work disruption, without incurring any liability." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=47660815 |
| C19 | competitor | verified_live (weight 0) | 0.0 | - | "- NudgePe, my own SaaS that chases late invoices automatically (Next.js, FastAPI, PostgreSQL, Supabase)." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=50495351 |
| C2 | pain | verified_live (weight 0) | 0.0 | - | "I sent him the invoice yesterday after getting a confirmation from him, but he not paid yet." <br>off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/9768/client-feels-he-is-doing-a-favor-on-me-by-paying-invoice-because-his-requirement |
| C4 | pain | verified_live (weight 0) | 0.0 | - | "This reduces the need for manual follow-ups or switching between tools, making it easier for freelancers to get paid on time." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=42914012 |

### Sources

- [C7] https://news.ycombinator.com/item?id=43381182 (verified_live, weight 1.0)
- [C8] https://news.ycombinator.com/item?id=43381182 (verified_live, weight 1.0)
- [C11] https://news.ycombinator.com/item?id=46771990 (verified_live, weight 1.0)
- [C6] https://news.ycombinator.com/item?id=43381182 (verified_live, weight 1.0)
