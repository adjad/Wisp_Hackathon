# Workflow20 implementation checkpoint

This is work in progress, not a claim that all20 outcomes are complete. The
portable corpus contains597 cases,500 positive variations including100 heldout
positives, across20 families. Corpus validation does not establish execution
accuracy. Model qualification has not run. New publication targets the user's
Wisp_Hackathon repository; original Wisp main remains unchanged.

| Family | Current implementation/evidence | Remaining completion work |
|---|---|---|
| 01 Overview | Personal compound source constraints; single-source shortcut cannot swallow another requested source | Source-backed final answer and partial-source end-to-end grading |
| 02 Daily summary | Existing composite daily_brief; protected compound read entry point | Full summary content/coverage and local-model qualification |
| 03 Time ranges | Existing exact calendar ranges; new exact week/month availability | Overlap/long-event range matrix and final answer grading |
| 04 CA weather |20 city names, aliases/four typo repairs, provider city/state/country validation;175 focused offline tests | Real provider/network behavior; arbitrary misspellings remain unsupported |
| 05 Priorities | Existing source tools/menu plus compound source obligations | Structured task ownership/due-date extraction, ranking and source-backed final answer |
| 06 Contact said | Strict query/conversation misses; identity preserved; Messages regression suite | All contact/time/topic phrase binding and final answer verification |
| 07 Thread/group recap | Cached chronological email bodies, account ambiguity and bounded-history disclosures | Real full-thread linkage/history retrieval; summary reasoning qualification |
| 08 Groceries | Existing Notes/Reminders reads with distinct sources | Checked items, quantities, list conflicts/deduplication in final synthesis |
| 09 Event time | Existing literal event lookup and current source reads | Ambiguity/updated event final answers across variations |
| 10 Reminder/event create | Existing native bridge/confirmation/persistence | Synthetic approved completion matrix; recurrence/calendar selection unsupported |
| 11 SFO arrival | Bounded traffic/current-location provider contract with fake-provider tests | Actual native provider integration; default provider unavailable, interface alone is not completion |
| 12 Draft/send/schedule | Existing grounded workflows and durable approval-bound effects | Cross-source composition qualification, revised recipient approval tests; scheduled threaded replies unsupported |
| 13 Unsubscribe | Truthful sender/account-bound unverified candidate preparation; no false success | Actual verified unsubscribe provider and historical-open evidence unavailable |
| 14 Files | Existing preview/snapshot-bound glob organization | Semantic/date categorization and completeness/conflict outcome matrix |
| 15 Personal knowledge/followups | Explicit memory tools, scoped reads and draft primitives | Comprehensive selected-source index/style/followup/receipt workflows are not implemented by this checkpoint |
| 16 Meeting | Existing personal calendar block and separate message/draft | Attendee invitation provider, after-event-end resolution, complete meeting workflow |
| 17 Fuzzy test time | Bounded subject typo/test-exam synonyms; quiz/midterm/final distinctions; multiple identities retained | Natural request binding and end-to-end ambiguity/answer tests |
| 18 Unread catchup | Actual unread Messages filtering; unknown-state/partial coverage; unread+date email intersection; shared basic direct reads | All qualified scope bindings and complete grounded catchup grading |
| 19 Availability message | Fresh exact-day/week/month availability uses real end times and overlap snapshots | Calendar-grounded message composition, privacy and approval revision tests |
| 20 Pending actions | Existing durable queue/list/cancel primitives | Bounded status history/full body inspection and lost-receipt truthfulness |

## Evidence boundaries

- Focused tests run over fake readers/providers or isolated SQLite. No personal
  reads, real communications, native permissions, model calls or live weather.
- Header digests cannot prove body-only deadlines. Corrected fixtures require
  body reads. Historical superseded thread proposals are allowed only with
  explicit supersession provenance.
- Route diagnostic tool availability, deterministic argument binding, actual
  tool semantics and full model-assisted execution are different measurements.
- Unsupported handling can pass safety while failing desired capability. Unrun
  cases never count as passes. Performance cannot pass without correctness.
- Native application acceptance is different from recipient delivery. Unknown
  outcomes must remain unknown and must not trigger an automatic resend.
- iPhone has separate ios/** ownership and its own build evidence; Mac regression
  results do not qualify iPhone native data access or local inference performance.

See CONTRACT.md for fixture and observation format. Use the benchmark runner's
validate/routes/grade modes explicitly; grade accepts externally supplied traces
and does not itself prove their execution provenance.
