# Gate 1 calibration run

Model: `nvidia/nemotron-3-ultra-550b-a55b` on NVIDIA's free tier. Live mode (variant 1 only). Thresholds unchanged (`config/gates.yaml`). The expected outcome for each idea was written before the run and is an ASSUMPTION (an informed prior, not ground truth).

**Agreement with the prior: 5 of 10.** Median time to a verdict: 76 s.

| Idea | Expected (ASSUMPTION) | Gate 1 | Rule | Complaints counted | Coverage | Places | People who'd pay | Competitors | Time | Run |
|---|---|---|---|---|---|---|---|---|---|---|
| late-payments | go | **stop** | rule_3 | 2.0 | 1.0 | 2 | 1 | 6 | 75 s | `r20261117-100427-b223` |
| soc2 | go | **stop** | rule_3 | 0 | 0.6 | 0 | 0 | 1 | 76 s | `r20261117-100545-ae01` |
| heroku-migration | go | **repeat** | rule_2 | 0 | 0.2 | 0 | 0 | 2 | 54 s | `r20261117-100703-a5c0` |
| interview-prep | go | **repeat** | rule_2 | 1.0 | 0.4 | 1 | 0 | 0 | 74 s | `r20261117-100800-144a` |
| k8s-costs | repeat | **repeat** | rule_2 | 0 | 0.0 | 0 | 0 | 0 | 115 s | `r20261117-100918-b50c` |
| wallpapers | stop | **repeat** | rule_2 | 0 | 0.4 | 0 | 0 | 3 | 73 s | `r20261117-101116-279e` |
| quotes-ebook | stop | **stop** | rule_3 | 0 | 0.6 | 0 | 0 | 0 | 97 s | `r20261117-101231-cb31` |
| crosswords | repeat | **repeat** | rule_2 | 0 | 0.0 | 0 | 0 | 0 | 53 s | `r20261117-101412-f514` |
| plant-tracker | repeat | **repeat** | rule_2 | 0 | 0.2 | 0 | 0 | 4 | 112 s | `r20261117-101508-c0ac` |
| dog-groomers | repeat | **repeat** | rule_2 | 0 | 0.0 | 0 | 0 | 0 | 88 s | `r20261117-101703-4efa` |

## Confusion matrix (rows: expected, columns: gate)

| expected \ gate | go | pivot | repeat | stop |
|---|---|---|---|---|
| go | 0 | 0 | 2 | 2 |
| pivot | 0 | 0 | 0 | 0 |
| repeat | 0 | 0 | 4 | 0 |
| stop | 0 | 0 | 1 | 1 |

## Reading it

- The gate is deliberately conservative: it never says GO on silence or on product launches alone; it needs people describing the problem in their own words, from at least two places.
- REPEAT means the public sources can't see the market well enough; the next step is the 5-interview kit, not a verdict on the idea.
- Disagreements are listed as they happened; no threshold or rule was changed to make them agree.
