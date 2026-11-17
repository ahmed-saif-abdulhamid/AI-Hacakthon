# Phase 1 gate: evidence decision

## Outcome: STOP

> **In plain words:** People discuss this topic, but ProveIt found no one clearly describing the problem, against the 6 it set as the bar before searching. Recommendation: don't build this as it stands.

- **Reason:** weak_pain_evidence
- **Rule fired:** rule_3
- **Next step:** -
- **Recommendation:** The topic is discussed (coverage 1.0), but verified pain signals are 0.5, below 3 and far below the pre-registered 6. Recommend: do not build this. (STOP for variant 1; the other angles were scored but not researched.)
- **Variant researched:** 1. Late-Payment Follow-Up Toolkit
- **Pre-registered thresholds SHA-256:** `123b85bcf0e37ce958ab6d76fd569f17ebdf0ad55803378ace5b75c8d5826dec`
- **Goalpost moved:** false
- **Founder decision:** pending

Thresholds are team defaults (ASSUMPTION), registered before any source was called.

## Metrics vs thresholds

| Check | Value | Threshold | Pass |
|---|---|---|---|
| sourced_pain (weighted) | 0.5 | >= 6 | no |
| distinct_sources | 1 | >= 2 | no |
| recent_share (<= 24 months) | 1.0 | >= 0.5 | yes |
| wtp_signals | 0 | >= 1 | no |
| competitors (distinct, verified) | 3 | in [1, 15] | yes |
| founder_fit (0-5, code) | 5.0 | >= 3 | yes |
| coverage | 1.0 | >= 0.5 | yes |

Claims: 13 total, 3 verified live, 10 archived matches, 0 unverified.

## Advocate (case for GO)

- ASSUMPTION: Freelancers report persistent late-payment friction and uncertainty about follow-up cadence.
- Existing platforms embed payment tracking and overdue alerts, proving demand for integrated tooling.[C9]
- ASSUMPTION: A low-cost template and workflow kit fits the founder's writing and spreadsheet skills with a $300 budget.

## Skeptic (case for STOP)

- ASSUMPTION: Only one distinct source and zero willingness-to-pay signals indicate the pain is anecdotal, not a validated market need.
- ASSUMPTION: Three live competitors already embed automated reminders and overdue analytics directly into invoicing platforms.
- ASSUMPTION: Founder's freelance dev background gives domain knowledge but no track record building or selling SaaS products.

The arguments are model-written and decide nothing; `gates.py` applies the rule precedence.

## Source coverage

| Source | Query | OK | Hits | On-topic | Covered |
|---|---|---|---|---|---|
| hn | clients pay invoices late | True | 19 | 8 | True |
| hn | chasing overdue payments | True | 17 | 13 | True |
| hn | forgot to send reminder | True | 19 | 16 | True |
| stackexchange | invoice reminder @ freelancing | True | 7 | 7 | True |
| stackexchange | clients pay invoices @ freelancing | True | 10 | 5 | True |

## Claim ledger (this variant)

| ID | Kind | Status | Weight | Cue | Quote | Source |
|---|---|---|---|---|---|---|
| C12 | competitor | VERIFIED_LIVE | 1.0 | - | "For example, when creating an invoice, the system can tell you that the client has overdue payments or that the new invoice is 40% above their usual average."  | https://news.ycombinator.com/item?id=47427522 |
| C13 | competitor | VERIFIED_LIVE | 1.0 | - | "These are now the clauses we require in every project we do: - Payment is due X days after receipt of invoice, or immediately after the consultant has addressed any quality issues, whichever is sooner - Late payment shal..."  | https://news.ycombinator.com/item?id=47660815 |
| C9 | competitor | VERIFIED_LIVE | 1.0 | - | "Integrated Invoicing & Payments: Beyond project tracking, clients can pay invoices directly through the platform. This reduces the need for manual follow-ups or switching between tools, making it easier for freelancers t..."  | https://news.ycombinator.com/item?id=42914012 |
| C3 | pain | ARCHIVED_MATCH | 0.5 | overdue | "Should I increase the invoice payment period or keep sending personalised reminders once overdue? I feel that if I increase the invoice payment period, they will be overdue the new period too." <br>page unreachable; archived match | https://freelancing.stackexchange.com/questions/11002/client-always-pay-but-after-due-late |
| C1 | pain | archived_match (weight 0) | 0.0 | - | "I invoice them every 2 weeks. The invoice mentions a 13-day period to pay. The invoicing software sends a reminder email every 5 days." <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/11002/client-always-pay-but-after-due-late |
| C10 | pain | archived_match (weight 0) | 0.0 | - | "I sent one after 17 days, which was viewed but not responded to. No response after a reminder sent the day after." <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/10192/client-hasnt-responded-to-invoice-company-has-potentially-conflicting-policies |
| C11 | pain | archived_match (weight 0) | 0.0 | - | "I invoiced them a couple weeks ago and they've gone pretty quiet ever since." <br>page unreachable; archived match; off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/9687/chasing-debts-during-coronavirus-lockdown-uk |
| C2 | pain | archived_match (weight 0) | 0.0 | - | "Later, they started paying after 14 days (1-2 days overdue every time)." <br>page unreachable; archived match; off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/11002/client-always-pay-but-after-due-late |
| C4 | pain | archived_match (weight 0) | 0.0 | - | "I'm having trouble getting paid for an invoice that a client owes me (just £100). He has started ignoring my phonecalls and texts and has never been very good over email to begin with." <br>page unreachable; archived match; off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/6521/small-claims-court-for-unpaid-small-invoice-uk |
| C5 | wtp | archived_match (weight 0) | 0.0 | - | "I'm starting to lose patience in chasing for such a small amount of money and am tempted to go through the small claims court - https://www.gov.uk/make-court-claim-for-money/overview It would cost me £25 if I fill the fo..." <br>page unreachable; archived match; off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/6521/small-claims-court-for-unpaid-small-invoice-uk |
| C6 | pain | archived_match (weight 0) | 0.0 | - | "Are there a certain amount of reminders that I need to send the client? and how overdue does the invoice need to be?" <br>page unreachable; archived match; a question, not someone's own experience | https://freelancing.stackexchange.com/questions/6521/small-claims-court-for-unpaid-small-invoice-uk |
| C7 | pain | archived_match (weight 0) | 0.0 | - | "The invoice I sent was in last December and have been asking for it to be paid for nearly a year now." <br>page unreachable; archived match; off topic for this variant (code keyword check) | https://freelancing.stackexchange.com/questions/7305/client-refusing-to-pay-threatening-to-involve-lawyer |
| C8 | pain | archived_match (weight 0) | 0.0 | - | "After regular reminders of the invoice the client is now saying I breached the contract terms by not completing the job, something that isn't covered in the contract, and now is saying he will get his lawyer involved." <br>page unreachable; archived match; label not confirmed by code | https://freelancing.stackexchange.com/questions/7305/client-refusing-to-pay-threatening-to-involve-lawyer |

### Sources

- [C9] https://news.ycombinator.com/item?id=42914012 (verified_live, weight 1.0)
