# Phase 2 gate: demand

## Outcome: REPEAT

- **Reason:** insufficient_evidence
- **Rule fired:** g2_no_real_traffic
- **Next step:** share_landing_page_publicly
- **Recommendation:** 0 real sign-ups against a target of 100 in 14 days. Public hosting is STUBBED and test sign-ups are excluded, so demand is not yet proven. Continuing needs a logged founder override.
- **Founder decision:** overridden against the evidence (logged). Reason: Continue the preview to Phases 3-6 for the demo; 0 real sign-ups, demand not proven
- **Thresholds SHA-256:** `b367a0d1338c03a8f7d6318d971398eb4139dff4b5fc0ed3444023704ce5ef90`

## Metrics

- real_signups: 0
- test_signups_excluded: 0
- visits: 0
- public_hosting: STUBBED

## Thresholds

- waitlist_target: 100
- window_days: 14
- min_visits_for_rate: 200
- min_conversion: 0.1

## Failed checks

- waitlist_target

Test sign-ups are excluded from every gate while public hosting is STUBBED. Continuing past this gate needs a logged founder override; Phases 3-5 are then a preview: demand not yet proven.
