# Phase 6, step 3: Metrics plan

What the analyst reads after launch, where each number comes from, and the bar it is held to. Every bar is in config/gates.yaml, hashed with the brief before the run started.

| Metric | Now | Bar | Read from | Bar set in |
|---|---|---|---|---|
| Real waitlist sign-ups | 0 | >= 100 in 14 days | signups table, test=false | gates.yaml gate2_demand |
| Landing-page conversion | n/a | >= 10% after 200 visits | visits and signups, test=false | gates.yaml gate2_demand |
| Real orders | 0 | >= 5 in 30 days | orders table, test=false | gates.yaml gate6_operate (ASSUMPTION) |
| Refund rate | n/a | <= 10% | refunds joined to real orders | gates.yaml gate6_operate (ASSUMPTION) |
| Test orders (never counted) | 1 | - | MOCKED payment test | - |

## Decision rule (code, first match wins)

1. Real orders >= 5 and refund rate <= 10%: **persevere** (GO).
2. Real orders >= 5 but refund rate above 10%: **pivot** the product (buyers came, the product did not keep them); return to Phase 3.
3. 30 days after launch, real sign-ups under 30% of the waitlist target and the order bar not met: **stop**.
4. Otherwise: **not enough data** (REPEAT: keep collecting, change nothing).
