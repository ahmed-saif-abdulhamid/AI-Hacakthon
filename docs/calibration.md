# Calibration notes

Calibration changes the cue lexicons and the relevance rule, never the gate thresholds, and happens before the committed runs.

| Date | Change | Why |
|---|---|---|
| 2026-11-17 | Added `idea`, `offer` to the product-context words of guard rule set B | A brief written as "Idea: printed t-shirts ..." had no other product word, so an excluded category slipped through. Found by the must-refuse set. |
| 2026-11-17 | Allow-list accepts hyphenated "shipping-a-side-project" | A must-pass brief was sent to the ask-the-founder tier. |
| 2026-11-17 | Rule set A: a number followed by "reviews / testimonials / ratings" is a fabrication request | Typo variant "Write 50 fiv-star reviewz" was missed. |
| 2026-11-17 | Hacker News queries use Algolia `optionalWords` | Algolia needs every word by default, so 3-4 word queries often returned 0 records; code's on-topic check still filters precision. Found on the first real weak-brief run (coverage 0.33). |
| 2026-11-17 | Scout prompt: the job to be done must name the product's concrete objects | The Scout wrote "boost daily mood with positive visuals", which shares no keywords with posts about quote wallpapers, so relevant posts could not count. |
| 2026-11-17 | Researcher output cap raised (num_predict 900 -> 2000, at most 15 claims) | The first strong-brief run returned truncated JSON; rule 0 correctly gave REPEAT model_failure instead of a STOP. |
| 2026-11-17 | Pain cues: added tired of, sick of, fed up, takes forever, a mess, clunky, painful | "tired of managing client projects through a mix of email threads" was rejected as "label not confirmed by code". |
| 2026-11-17 | Scout prompt: pain queries must be phrased as complaints (task nouns + a problem word), as the plan specifies | The Scout produced solution-phrased queries such as "client onboarding checklist". |
| 2026-11-17 | Sentences shown to the model must be mostly letters (no code, tables or ASCII diagrams) | An ASCII architecture diagram was counted as a competitor claim. |
| 2026-11-17 | On-topic check reads the quote together with its thread title; the cue must still be in the quote | "Each month there is at least one client who does not pay my invoice." shared only one keyword with the variant, because a single sentence rarely repeats the segment's words. |
| 2026-11-17 | Pain cues: added despise, awkward, infuriating, stressful, dread, unpaid, overdue, never pay/reply/send, doesn't pay/work/help | "I absolutely despise sending follow up reminders it feels needy, awkward" was rejected as "label not confirmed by code". |
| 2026-11-17 | The rule-0 missed-sentence check stays sentence-level (no thread title) | With the title included, code flagged off-topic lines inside on-topic threads ("manually copy paste codes") as missed evidence, so rule 0 fired on a model that had chosen correctly. |
| 2026-11-17 | Rule-0 missed-sentence proxy ignores questions and bullet lines and uses only strong payment words (paid, would pay, pay for, bought, $N) | On the strong brief all six "missed" sentences were feature bullets, survey questions or "charge" used for invoice line items; the model had been right to skip them. |
| 2026-11-17 | Researcher reads 4 threads per call instead of 12 | The 4B model selected far more of the real evidence from short lists (34 vs about 15 claims on the same hits). |
| 2026-11-17 | Strategist and Launcher prompts: describe the files, never automatic behaviour or outcomes; FAQ question/answer order fixed by code | Founder review of the first landing page found swapped FAQ fields and software-like claims ("tracks overdue invoices automatically", "reduces missed payments"); the founder rejected it and it was regenerated. |
| 2026-11-17 | Pricer counts each (source URL, price) once; policy drafts replace any email address with a placeholder | Founder review at Gate 4 found one HN sentence counted twice as two price points, and an invented support address in the refund draft; the founder rejected Gate 4 and Phase 4 was redone. |
| 2026-11-17 | Store page "What is included" lists exactly the built modules (set by code) | Founder review found five invented items on the store page for a three-module product; the founder rejected it and it was regenerated. |

## Brief history

- Weak brief (motivational lock-screen wallpapers): STOP on every run after the first source fix.
- First strong brief, a client-onboarding toolkit for freelance web designers: STOP (rule 3) twice with coverage 1.0 and 0 counted pain. The topic is discussed, but our sources show little complaint about it. The complaints that did appear were about clients paying late, so the strong brief was changed to a late-payment follow-up toolkit. Changing the brief is allowed; thresholds were never changed.

After these changes all briefs were re-run from scratch.

No gate threshold was changed. The held-out trick set (`evals/trick_prompts_heldout.yaml`) was never used for any change above.
