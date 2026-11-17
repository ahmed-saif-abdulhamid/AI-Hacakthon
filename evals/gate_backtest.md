# Gate 1 calibration run

Model: `nvidia/nemotron-3-ultra-550b-a55b` on NVIDIA's free tier. Live mode (variant 1 only). Thresholds unchanged (`config/gates.yaml`). The expected outcome for each idea was written before the run and is an ASSUMPTION (an informed prior, not ground truth).

**Agreement with the prior: 5 of 10.** Median time to a verdict: 101 s.

| Idea | Expected (ASSUMPTION) | Gate 1 | Rule | Complaints counted | Coverage | Places | People who'd pay | Competitors | Time | Run |
|---|---|---|---|---|---|---|---|---|---|---|
| late-payments | go | **stop** | rule_3 | 1.0 | 1.0 | 1 | 0 | 3 | 70 s | `r20261117-133831-9ac6` |
| soc2 | go | **repeat** | rule_2 | 0 | 0.4 | 0 | 0 | 0 | 98 s | `r20261117-133944-5725` |
| heroku-migration | go | **repeat** | rule_2 | 0 | 0.4 | 0 | 0 | 1 | 129 s | `r20261117-134126-80a9` |
| interview-prep | go | **repeat** | rule_0 | 0 | 0.6 | 0 | 0 | 0 | 230 s | `r20261117-134337-509a` |
| k8s-costs | repeat | **repeat** | rule_0 | 0 | 0.2 | 0 | 0 | 0 | 80 s | `r20261117-134731-04f5` |
| wallpapers | stop | **repeat** | rule_2 | 0 | 0.2 | 0 | 0 | 3 | 101 s | `r20261117-134854-68ce` |
| quotes-ebook | stop | **stop** | rule_3 | 0 | 0.6 | 0 | 0 | 0 | 173 s | `r20261117-135038-4424` |
| crosswords | repeat | **repeat** | rule_2 | 0 | 0.0 | 0 | 0 | 0 | 19 s | `r20261117-135334-3242` |
| plant-tracker | repeat | **repeat** | rule_2 | 0 | 0.2 | 0 | 0 | 0 | 131 s | `r20261117-135355-b5d2` |
| dog-groomers | repeat | **repeat** | rule_2 | 0 | 0.0 | 0 | 0 | 0 | 81 s | `r20261117-135609-fc69` |

## Confusion matrix (rows: expected, columns: gate)

| expected \ gate | go | pivot | repeat | stop |
|---|---|---|---|---|
| go | 0 | 0 | 3 | 1 |
| pivot | 0 | 0 | 0 | 0 |
| repeat | 0 | 0 | 4 | 0 |
| stop | 0 | 0 | 1 | 1 |

## Reading it

- The gate is deliberately conservative: it never says GO on silence or on product launches alone; it needs people describing the problem in their own words, from at least two places.
- REPEAT means the public sources can't see the market well enough; the next step is the 5-interview kit, not a verdict on the idea.
- Disagreements are listed as they happened; no threshold or rule was changed to make them agree.
