# Gate 1 calibration run

Model: `nvidia/nemotron-3-ultra-550b-a55b` on NVIDIA's free tier. Live mode (variant 1 only). Thresholds unchanged (`config/gates.yaml`). The expected outcome for each idea was written before the run and is an ASSUMPTION (an informed prior, not ground truth).

**Agreement with the prior: 5 of 10.** Median time to a verdict: 116 s.

| Idea | Expected (ASSUMPTION) | Gate 1 | Rule | Complaints counted | Coverage | Places | People who'd pay | Competitors | Time | Run |
|---|---|---|---|---|---|---|---|---|---|---|
| late-payments | go | **error** |  | None | None | None | None | None | 116 s | `r20261117-130140-32c6` |
| soc2 | go | **stop** | rule_3 | 0 | 0.6 | 0 | 0 | 1 | 165 s | `r20261117-130339-b6aa` |
| heroku-migration | go | **repeat** | rule_2 | 0 | 0.2 | 0 | 0 | 1 | 62 s | `r20261117-130627-1592` |
| interview-prep | go | **repeat** | rule_0 | 0 | 0.2 | 0 | 0 | 0 | 78 s | `r20261117-130732-4141` |
| k8s-costs | repeat | **repeat** | rule_2 | 0 | 0.2 | 0 | 0 | 0 | 89 s | `r20261117-130853-8145` |
| wallpapers | stop | **error** |  | None | None | None | None | None | 213 s | `r20261117-131025-4a82` |
| quotes-ebook | stop | **stop** | rule_3 | 0 | 0.6 | 0 | 0 | 1 | 196 s | `r20261117-131401-bcc7` |
| crosswords | repeat | **repeat** | rule_2 | 0 | 0.0 | 0 | 0 | 0 | 56 s | `r20261117-131720-182a` |
| plant-tracker | repeat | **repeat** | rule_2 | 0 | 0.2 | 0 | 0 | 0 | 185 s | `r20261117-131818-6da0` |
| dog-groomers | repeat | **repeat** | rule_2 | 0 | 0.0 | 0 | 0 | 0 | 70 s | `r20261117-132127-a379` |

## Confusion matrix (rows: expected, columns: gate)

| expected \ gate | go | pivot | repeat | stop |
|---|---|---|---|---|
| go | 0 | 0 | 2 | 1 |
| pivot | 0 | 0 | 0 | 0 |
| repeat | 0 | 0 | 4 | 0 |
| stop | 0 | 0 | 0 | 1 |

## Reading it

- The gate is deliberately conservative: it never says GO on silence or on product launches alone; it needs people describing the problem in their own words, from at least two places.
- REPEAT means the public sources can't see the market well enough; the next step is the 5-interview kit, not a verdict on the idea.
- Disagreements are listed as they happened; no threshold or rule was changed to make them agree.
