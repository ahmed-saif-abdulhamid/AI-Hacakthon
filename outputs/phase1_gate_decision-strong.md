# Phase 1 gate: evidence decision

## Outcome: REPEAT

> **In plain words:** The public forums searched can't see this market well enough to call it either way. That is not proof nobody wants it: the next step is five short conversations (see the interview kit).

- **Reason:** insufficient_evidence
- **Rule fired:** rule_2
- **Next step:** mom_test_interviews
- **Recommendation:** Our public sources cannot see this market well enough (coverage 0.33 < 0.5). This is not evidence of absence. Run 5 Mom Test interviews.
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
| recent_share (<= 24 months) | 1.0 | >= 0.5 | yes |
| wtp_signals | 0 | >= 1 | no |
| competitors (distinct, verified) | 1 | in [1, 15] | yes |
| founder_fit (0-5, code) | 5.0 | >= 3 | yes |
| coverage | 0.33 | >= 0.5 | no |

Claims: 9 total, 9 verified live, 0 archived matches, 0 unverified.

Code-qualified sentences not selected by the model: H57.S12, H69.S4.

## For and against

Not written for this verdict: the public sources gave too little to argue about, or the research did not come back clean. The arguments never decide a checkpoint.

## Source coverage

| Source | Query | OK | Hits | On-topic | Covered |
|---|---|---|---|---|---|
| hn | forgot to follow up invoices | True | 20 | 1 | False |
| hn | chasing overdue payments | True | 17 | 13 | True |
| hn | clients pay invoices late | True | 19 | 6 | True |
| hn | freelance developers and | True | 20 | 2 | False |
| stackexchange | invoice reminder templates @ freelancing | True | 0 | 0 | False |
| stackexchange | forgot follow invoices @ freelancing | True | 0 | 0 | False |

## Claim ledger (this variant)

| ID | Kind | Status | Weight | Cue | Quote | Source |
|---|---|---|---|---|---|---|
| C18 | pain | VERIFIED_LIVE | 1.0 | a mess | "If they reply with some nonsense about check runs and things being sent out on a Thursday, respond with a message clarifying when you expect payment based on what they said. If no reply within a day or two escalate -- se..."  | https://news.ycombinator.com/item?id=47639489 |
| C21 | competitor | VERIFIED_LIVE | 1.0 | - | "For example, when creating an invoice, the system can tell you that the client has overdue payments or that the new invoice is 40% above their usual average."  | https://news.ycombinator.com/item?id=47427522 |
| C19 | pain | verified_live (weight 0) | 0.0 | - | "Do not allow subcontractors to send their own invoices, you must do this yourself to ensure that all communication is exactly on time and never late. Lateness and inconsistency on your side erodes your ability to run a t..." <br>label not confirmed by code | https://news.ycombinator.com/item?id=47638781 |
| C20 | pain | verified_live (weight 0) | 0.0 | - | "Seriously though, people aren't paying because they're not paying -- not because they somehow forgot. They're assholes. So treat them like assholes -- stop providing services the second their payment is late. Demand paym..." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=47639489 |
| C22 | pain | verified_live (weight 0) | 0.0 | - | "If your customer is not communicating with you about invoices THEY ARE NOT SOLVENT. If payments are slowing down and tardiness is increasing, they are not being forgetful, THEY ARE RUNNING OUT OF MONEY." <br>label not confirmed by code | https://news.ycombinator.com/item?id=47638781 |
| C23 | pain | verified_live (weight 0) | 0.0 | - | "In some cases you just have to treat non payment as part of the cost of doing business." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=47639489 |
| C24 | competitor | verified_live (weight 0) | 0.0 | - | "- NudgePe, my own SaaS that chases late invoices automatically (Next.js, FastAPI, PostgreSQL, Supabase)." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=50495351 |
| C25 | pain | verified_live (weight 0) | 0.0 | - | "After 7 years of freelancing and building enterprise platforms, I realized I was spending 20% of my time on "Shadow Admin" work-drafting contracts, compliance, and chasing invoices." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=46839109 |
| C26 | pain | verified_live (weight 0) | 0.0 | - | "These are now the clauses we require in every project we do: - Payment is due X days after receipt of invoice, or immediately after the consultant has addressed any quality issues, whichever is sooner - Late payment shal..." <br>label not confirmed by code | https://news.ycombinator.com/item?id=47660815 |

### Sources

No statement in this file carries a verified citation; every claim above is labelled ASSUMPTION.
