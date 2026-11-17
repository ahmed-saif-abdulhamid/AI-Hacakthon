# Phase 1 gate: evidence decision

## Outcome: REPEAT

> **In plain words:** The public forums searched can't see this market well enough to call it either way. That is not proof nobody wants it: the next step is five short conversations (see the interview kit).

- **Reason:** insufficient_evidence
- **Rule fired:** rule_2
- **Next step:** mom_test_interviews
- **Recommendation:** Our public sources cannot see this market well enough (coverage 0.4 < 0.5). This is not evidence of absence. Run 5 Mom Test interviews.
- **Variant researched:** 3. Project Deposit & Milestone Tracker
- **Pre-registered thresholds SHA-256:** `123b85bcf0e37ce958ab6d76fd569f17ebdf0ad55803378ace5b75c8d5826dec`
- **Goalpost moved:** false
- **Founder decision:** overridden against the evidence (logged). Reason: I accept the evidence is weak; I want a landing page to test demand directly with freelancers I know.

Thresholds are team defaults (ASSUMPTION), registered before any source was called.

## Metrics vs thresholds

| Check | Value | Threshold | Pass |
|---|---|---|---|
| sourced_pain (weighted) | 0 | >= 6 | no |
| distinct_sources | 0 | >= 2 | no |
| recent_share (<= 24 months) | 0.0 | >= 0.5 | no |
| wtp_signals | 0 | >= 1 | no |
| competitors (distinct, verified) | 0 | in [1, 15] | no |
| founder_fit (0-5, code) | 5.0 | >= 3 | yes |
| coverage | 0.4 | >= 0.5 | no |

Claims: 4 total, 4 verified live, 0 archived matches, 0 unverified.

## For and against

Not written for this verdict: the public sources gave too little to argue about, or the research did not come back clean. The arguments never decide a checkpoint.

## Source coverage

| Source | Query | OK | Hits | On-topic | Covered |
|---|---|---|---|---|---|
| hn | clients skip deposit payment | True | 18 | 10 | True |
| hn | milestone payments delayed | True | 18 | 7 | True |
| hn | forgot which milestone paid | True | 20 | 1 | False |
| stackexchange | project payment tracker @ freelancing | False | 0 | 0 | False | Client error '429 Too Many Requests' for url 'https://api.st
| stackexchange | clients skip deposit @ freelancing | False | 0 | 0 | False | Client error '429 Too Many Requests' for url 'https://api.st

## Claim ledger (this variant)

| ID | Kind | Status | Weight | Cue | Quote | Source |
|---|---|---|---|---|---|---|
| C14 | pain | verified_live (weight 0) | 0.0 | - | "Answers: AWS doesn't give you a cent back, under any circumstances, does NOT get your servers back online but MAY give you 20% reduction on your future bill (and for customers in the UAE with the Iran war, they didn't) S..." <br>label not confirmed by code | https://news.ycombinator.com/item?id=50334908 |
| C15 | pain | verified_live (weight 0) | 0.0 | - | "Failing to get a permit is not an act of god, having to pay even when the site does t have power is poor milestone / payment planning." <br>label not confirmed by code | https://news.ycombinator.com/item?id=49844201 |
| C16 | pain | verified_live (weight 0) | 0.0 | - | "As far as the client is concerned, payment is delayed until the requirements are met that were laid out in the statement of work." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=46195877 |
| C17 | pain | verified_live (weight 0) | 0.0 | - | "I have heard about projects at my current company where we have to give the client free work because the requirements weren't met within the time allotted." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=46195877 |

### Sources

No statement in this file carries a verified citation; every claim above is labelled ASSUMPTION.
