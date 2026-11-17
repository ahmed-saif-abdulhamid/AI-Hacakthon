# Phase 1 gate: evidence decision

## Outcome: STOP

> **In plain words:** People discuss this topic, but ProveIt found no one clearly describing the problem, against the 6 it set as the bar before searching. Recommendation: don't build this as it stands.

- **Reason:** weak_pain_evidence
- **Rule fired:** rule_3
- **Next step:** -
- **Recommendation:** The topic is discussed (coverage 0.6), but verified pain signals are 0, below 3 and far below the pre-registered 6. Recommend: do not build this. (STOP for variant 1; variants 2-3 not researched.)
- **Variant researched:** 1. 500 Entrepreneur Quote Cards
- **Pre-registered thresholds SHA-256:** `cfec66d88e212551767db9cc2758d72dbea2b4fae637d95843fbeeecb3ab9e31`
- **Goalpost moved:** false
- **Founder decision:** pending

Thresholds are team defaults (ASSUMPTION), registered before any source was called.

## Metrics vs thresholds

| Check | Value | Threshold | Pass |
|---|---|---|---|
| sourced_pain (weighted) | 0 | >= 6 | no |
| distinct_sources | 0 | >= 2 | no |
| recent_share (<= 24 months) | 0.0 | >= 0.5 | no |
| wtp_signals | 0 | >= 1 | no |
| competitors (distinct, verified) | 0 | in [1, 15] | no |
| founder_fit (0-5, code) | 4.0 | >= 3 | yes |
| coverage | 0.6 | >= 0.5 | yes |

Claims: 0 total, 0 verified live, 0 archived matches, 0 unverified.

## Advocate (case for GO)

- ASSUMPTION: The founder's Canva skills and $50 budget align well with creating simple quote cards for aspiring entrepreneurs.
- ASSUMPTION: Four hours per week is sufficient to design and schedule a steady stream of positive, shareable content.
- ASSUMPTION: A low-cost, design-focused approach minimizes risk while testing demand for entrepreneur-focused inspiration.

## Skeptic (case for STOP)

- ASSUMPTION: No sourced pain points or willingness-to-pay signals exist to validate demand for entrepreneur quote cards.
- ASSUMPTION: Founder has only basic Canva skills and $50 budget with 4 hours weekly, limiting production quality and marketing reach.
- ASSUMPTION: Zero distinct sources and competitors metric suggests either no market exists or opportunity is completely unproven.

The arguments are model-written and decide nothing; `gates.py` applies the rule precedence.

## Source coverage

| Source | Query | OK | Hits | On-topic | Covered |
|---|---|---|---|---|---|
| hn | quotes for instagram posts | True | 20 | 11 | True |
| hn | motivational content ideas | True | 20 | 4 | True |
| hn | daily quote graphics | True | 20 | 8 | True |
| stackexchange | quote graphics @ graphicdesign | True | 10 | 1 | False |
| stackexchange | quotes instagram posts @ graphicdesign | True | 0 | 0 | False |

## Claim ledger (this variant)

| ID | Kind | Status | Weight | Cue | Quote | Source |
|---|---|---|---|---|---|---|

### Sources

No statement in this file carries a verified citation; every claim above is labelled ASSUMPTION.
