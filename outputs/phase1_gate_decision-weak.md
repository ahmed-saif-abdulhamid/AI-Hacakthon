# Phase 1 gate: evidence decision

## Outcome: STOP

- **Reason:** weak_pain_evidence
- **Rule fired:** rule_3
- **Next step:** -
- **Recommendation:** The topic is discussed (coverage 0.67), but verified pain signals are 2.0, below 3 and far below the pre-registered 6. Recommend: do not build this. (STOP for variant 1; variants 2-3 not researched.)
- **Variant researched:** 1. 100 Motivational Quote Wallpapers Pack
- **Pre-registered thresholds SHA-256:** `4cce009ff2e69bd758f66990858db7a1dc62d9743bf4fa389c0bfb3f779426b0`
- **Goalpost moved:** false
- **Founder decision:** pending

Thresholds are team defaults (ASSUMPTION), registered before any source was called.

## Metrics vs thresholds

| Check | Value | Threshold | Pass |
|---|---|---|---|
| sourced_pain (weighted) | 2.0 | >= 6 | no |
| distinct_sources | 1 | >= 2 | no |
| recent_share (<= 24 months) | 1.0 | >= 0.5 | yes |
| wtp_signals | 1 | >= 1 | yes |
| competitors (distinct, verified) | 7 | in [1, 15] | yes |
| founder_fit (0-5, code) | 4.0 | >= 3 | yes |
| coverage | 0.67 | >= 0.5 | yes |

Claims: 15 total, 14 verified live, 1 archived matches, 0 unverified.

Code-qualified sentences not selected by the model: H7.S8.

## Advocate (case for GO)

- ASSUMPTION: Competitors offer motivational quotes and widgets, including AI-driven context and custom wallpapers, validating feature relevance [C1, C2, C3].
- ASSUMPTION: Users seek customization and motivation, with pain points in macOS and phone unlock friction [C10, C12].
- ASSUMPTION: Lifetime access requires selecting $0.00 option in paywall to complete free purchase [C5].

## Skeptic (case for STOP)

- ASSUMPTION: Missing evidence: No unique value proposition beyond existing competitor features.
- ASSUMPTION: Low founder fit: Pain points cited are generic and not uniquely tied to this product.
- ASSUMPTION: Crowded competition: 7 direct competitors offer similar features with stronger presence.

The arguments are model-written and decide nothing; `gates.py` applies the rule precedence.

## Source coverage

| Source | Query | OK | Hits | On-topic | Covered |
|---|---|---|---|---|---|
| hn | lock screen quotes mess | True | 20 | 20 | True |
| hn | motivational quotes chasing | True | 20 | 13 | True |
| stackexchange | motivational quote wallpapers @ webapps | True | 0 | 0 | False |

## Claim ledger (this variant)

| ID | Kind | Status | Weight | Cue | Quote | Source |
|---|---|---|---|---|---|---|
| C1 | competitor | VERIFIED_LIVE | 1.0 | - | "Features: - Add lock screen, home screen or today quote widgets."  | https://news.ycombinator.com/item?id=43148630 |
| C10 | pain | VERIFIED_LIVE | 1.0 | frustrat | "For years, I've been frustrated by the lack of customisation of macOS."  | https://news.ycombinator.com/item?id=45247396 |
| C11 | competitor | VERIFIED_LIVE | 1.0 | - | "However, through extensive reverse engineering of the macOS wallpaper system, I figured out a way to provide Backdrop wallpapers to the system in a way that allows them to play on the lock screen, and even appear in a cu..."  | https://news.ycombinator.com/item?id=45247396 |
| C12 | pain | VERIFIED_LIVE | 1.0 | sick of | "I finally built this app after many years of being sick of unlocking my phone every goddamn time I need to take or view my notes. It particularly sucks when I'm doing my grocery and going down the list."  | https://news.ycombinator.com/item?id=47467671 |
| C13 | competitor | VERIFIED_LIVE | 1.0 | - | "AmitGujar/Bink-Chrome-Extension: Bink makes your browser Homescreen Beautiful with Daily new Wallpapers and Motivational Quotes, Weather, and Much More."  | https://github.com/AmitGujar/Bink-Chrome-Extension |
| C14 | competitor | VERIFIED_LIVE | 1.0 | - | "yasincidem/AndroidOpenSourceMotivationApp: :muscle: A motivation app that contains wallpaper, quotes, videos"  | https://github.com/yasincidem/AndroidOpenSourceMotivationApp |
| C15 | competitor | VERIFIED_LIVE | 1.0 | - | "Akshayanvishaalb/quote-wallpaper: A Python-based dynamic wallpaper system for Ubuntu GNOME that displays motivational quotes, automatically updating the desktop wallpaper on login."  | https://github.com/Akshayanvishaalb/quote-wallpaper |
| C2 | competitor | VERIFIED_LIVE | 1.0 | - | "- AI feature to get more context on quotes and authors you like to further boost motivation."  | https://news.ycombinator.com/item?id=43148630 |
| C3 | competitor | VERIFIED_LIVE | 1.0 | - | "Users can fetch a random quote from a local JSON file or add their own, then create a personalized wallpaper with the chosen background color and motivational text."  | https://github.com/avril-o/positive-wallpaper-changer |
| C5 | wtp | VERIFIED_LIVE | 1.0 | $0 | "Important: You need to select $0.00 Lifetime option in the paywall and complete the free purchase in order to get the lifetime subscription."  | https://news.ycombinator.com/item?id=43148630 |
| C7 | competitor | VERIFIED_LIVE | 1.0 | - | "-1. Persistent Lock Screen Instruction (You Set This) During setup, EchoVaults lets you write a permanent message that stays visible on your phone's lock screen."  | https://news.ycombinator.com/item?id=44602658 |
| C9 | competitor | VERIFIED_LIVE | 1.0 | - | "Backdrop is my Live Wallpaper app for Mac, it can play video wallpapers on your desktop."  | https://news.ycombinator.com/item?id=45247396 |
| C4 | competitor | verified_live (weight 0) | 0.0 | - | "The app automatically updates the desktop wallpaper." <br>off topic for this variant (code keyword check) | https://github.com/avril-o/positive-wallpaper-changer |
| C6 | wtp | archived_match (weight 0) | 0.0 | - | "What you get every morning: - Local weather forecast for your area - Top stock market/financial moves - News headlines that matter - A motivational quote to start the day Looking for 23 more beta testers." <br>not live-checked (verify cap); label not confirmed by code | https://news.ycombinator.com/item?id=47496268 |
| C8 | pain | verified_live (weight 0) | 0.0 | - | "-2. They Must Unlock Your Phone (First Layer of Defense) EchoVaults doesn't bypass or weaken your device's native security." <br>off topic for this variant (code keyword check) | https://news.ycombinator.com/item?id=44602658 |

### Sources

No statement in this file carries a verified citation; every claim above is labelled ASSUMPTION.
