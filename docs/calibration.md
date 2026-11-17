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

## Round 2: hosted model and independent review (2026-11-17)

The model moved from a local 4B model to NVIDIA Nemotron 3 Ultra on NVIDIA's free hosted tier. Four independent reviews (a first-time founder, an investor, an accessibility and polish audit, and a compliance and stress test) found the problems below. Gate thresholds (`config/gates.yaml`) were not changed.

| Date | Change | Why (evidence) |
|---|---|---|
| 2026-11-17 | Relevance ignores generic business words (small, new, clients, forms, track, records, US, UK...) and needs two specific topic words, one of them about the job | A dog-groomer brief was marked "topic discussed" (coverage 0.67) by Hacker News posts that only shared generic words, so it got a STOP for the wrong reason. |
| 2026-11-17 | One comment counts as one complaint | Two sentences of the same Hacker News comment counted as two pain signals. |
| 2026-11-17 | Wikipedia context is shown only when the article shares two topic words and is not a list, disambiguation or media page | The strong market file quoted the article on the 2003 video game "Freelancer". |
| 2026-11-17 | Hacker News pain queries search comments, not stories | Stories are mostly product launches (competitor evidence); people describe their problems in replies. |
| 2026-11-17 | Posts with a complaint or payment cue are shown to the researcher first; GitHub repositories take at most 3 of 20 slots; batches of 7 threads | The 550B model handles longer lists; before this, repositories with keyword-dense titles crowded out comments. |
| 2026-11-17 | Stack Exchange quotes are re-checked through the official API | The HTML pages now sit behind a bot challenge (HTTP 403), so every Stack Exchange quote was wrongly downgraded to an archived match. |
| 2026-11-17 | Scout queries: complete phrases (no dangling "for"), five words at most; Stack Exchange site chosen by who the buyers are, from a list checked against the live site registry (`productivity` removed, `writers` corrected to `writing`) | Queries such as "intake form mess for"; a dog-groomer idea searched `freelancing`; two site names returned HTTP 400. |
| 2026-11-17 | Complaint cues gained common words (complicated, confusing, difficult, impossible, losing time, a chore, error-prone, costly, overkill) | Real complaints such as "notoriously hard" or "way more complicated" were not recognised. |
| 2026-11-17 | Rule 0's missed-sentence proxy counts only first-person sentences without links or hashtags | Marketing copy ("alerts you when overdue payments are detected", "Try free: ...") made rule 0 fire on a model that had chosen correctly. |
| 2026-11-17 | Live mode searches Hacker News 3 times and Stack Exchange twice (was 2 and 1); the researcher sees 20 posts (was 12) | Runtime caps only; they change how much is read, not the bar. |
| 2026-11-17 | Model calls are paced to 30 a minute with back-off on HTTP 429 and 5xx | In the first calibration run half the runs failed with "Too Many Requests". |
| 2026-11-17 | Weak brief changed from quote wallpapers to an ebook of inspirational quotes | On the hosted model the wallpaper idea gets REPEAT: the forums we search can't see that market, and the gate never says STOP on silence. The quotes ebook is discussed but nobody describes it as a problem. |

### Weak brief attempts on the final code (all kept in the database)

| Run | Gate 1 |
|---|---|
| `r20261117-105019-7a30` | STOP (rule 3: coverage 0.6, 1 complaint) |
| `r20261117-105214-47a5` | REPEAT (rule 2: coverage below 0.5) |
| `r20261117-105451-d4b0` | REPEAT (rule 2) |
| `r20261117-105529-93d0` | STOP (rule 3), committed |
| `r20261117-132732-0a2d` | REPEAT (rule 2), after the round-2 review fixes |
| `r20261117-132756-fbca` | REPEAT (rule 2), after the round-2 review fixes |

The variation comes from the Scout's search phrasing, which differs between calls even at temperature 0 on the hosted model. Neither outcome recommends building. The committed weak run stays `r20261117-105529-93d0`: every rule added after it only lowers complaint counts, so its STOP holds under the final code.

## Round 3: second independent review (2026-11-17)

| Date | Change | Why (evidence) |
|---|---|---|
| 2026-11-17 | Vendor pitches ("I'm building", "we built", "the idea came from", "I hear from", "Show HN") and feature bullets never count as complaints; they can still count as existing tools | The committed strong run counted PayPrompt's and Experi's launch posts as two of its "real complaints". |
| 2026-11-17 | A question never counts as a complaint; general words (manual, problem, overdue, wish, pain, expensive) count only in a first-person sentence | A survey question ("Do you track invoices manually?") was labelled a complaint. |
| 2026-11-17 | Payment-delay complaints are recognised ("not paid", "payment pending", "still waiting", "owes me", "ghosted") | A freelancer owed two $2,000 payments on Stack Exchange was given weight 0. |
| 2026-11-17 | Hacker News posts marked `[dead]` or `[flagged]` are dropped | Moderated-away posts were counted. |
| 2026-11-17 | The verdict is computed before the for-and-against debate, which is skipped when there is nothing to argue (rule 2 or rule 0) and can never fail a run; a retry reuses the search already made | A rate limit at the debate step stopped runs, and "Try again" re-ran the search and counted quotes twice. |
| 2026-11-17 | When the model is busy, the run waits 20, 40 and 60 seconds and retries the same step before asking the founder | Runs needed manual retries when other work shared the free tier. |
| 2026-11-17 | The launch-post copy rule also blocks invented history ("I got tired of", "I kept chasing", "after 7 years as") | The re-recorded strong run's first post draft invented the founder's frustration; the founder rejected it and it was redrafted. |

The committed strong run is now `r20261117-132954-34f7`: STOP at Gate 1 with one verified complaint against six; the founder's logged override; a preview through all six phases; the first store-and-post draft rejected for invented experience and redrafted.
