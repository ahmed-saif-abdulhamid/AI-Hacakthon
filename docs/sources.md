# Source adapters

| Source | Endpoint | Key | Live cap | Full cap | Counts toward coverage |
|---|---|---|---|---|---|
| Hacker News (Algolia) | `https://hn.algolia.com/api/v1/search` comments (the pipeline's default), last 24 months | none | 3 calls | 4 | yes |
| Stack Exchange | `https://api.stackexchange.com/2.3/search/advanced` on one site chosen by the Scout | optional free `SE_KEY` | 2 calls | 2 | yes |
| GitHub | `https://api.github.com/search/repositories` (competitor evidence) | optional free `GITHUB_TOKEN` | 1 call | 2 | no |
| SearXNG | `http://searxng:8080/search?format=json`, then the top result pages are fetched and split | none (self-hosted) | 2 calls + 4 pages | 3 + 6 | yes |
| Wikipedia | search + REST summary | none | context only | context only | no |
| Reddit | not used | - | STUBBED | STUBBED | no |

Responses are cached in `data/cache/` for six hours, which only helps repeated runs. A source that does not answer is reported as unavailable and lowers coverage; nothing is filled in.

Add a source by subclassing `sources.base.Source`, returning `(hits, SourceCall)` from `search()`, and setting `pain_capable` if its records can contain first-hand complaints.
