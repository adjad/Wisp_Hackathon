# Workflow20 implementation checkpoint

This is work in progress, not a claim that all 20 outcomes are complete. The
portable corpus contains 597 cases, 500 positive variations including 100 heldout
positives, across 20 families. Corpus validation does not establish execution
accuracy. Model qualification has not run. New publication targets the user's
Wisp_Hackathon repository; original Wisp main remains unchanged.

| Family | Current implementation/evidence | Remaining completion work |
|---|---|---|
| 01 Overview | Personal compound source constraints; single-source shortcut cannot swallow another requested source | Source-backed final answer and partial-source end-to-end grading |
| 02 Daily summary | Bounded composite daily_brief with source exclusions, current receipts, today Calendar and separate overdue/upcoming/undated reminders; shared daily/date-first briefing grammar and Calendar-only brief | Full summary content/coverage and local-model qualification |
| 03 Time ranges | Exact calendar ranges, noun-position cal/weekend questions resolve to Saturday–Sunday ISO ranges; week/month availability and ongoing/overnight overlap regressions | Full end-to-end final answer grading and real-source validation |
| 04 CA weather | 20 city names, aliases/four typo repairs, provider city/state/country validation; 175 focused offline tests | Real provider/network behavior; arbitrary misspellings remain unsupported |
| 05 Priorities | Bounded priorities route uses the requested daily_brief window plus separate overdue/undated tasks and Notes evidence | Structured task ownership/due-date extraction, ranking and source-backed final answer |
| 06 Contact said | Strict query/conversation misses; retrospective email/text questions stay reads; relationship questions remain private without saved contact metadata | All contact/time/topic/sender phrase binding and final answer verification |
| 07 Thread/group recap | Cached chronological email bodies, account ambiguity, bounded-history disclosures and explicit named chat/date bindings | Real full-thread linkage/history retrieval; sender-wide filtering and summary reasoning qualification |
| 08 Groceries | Existing Notes/Reminders reads with distinct sources | Checked items, quantities, list conflicts/deduplication in final synthesis |
| 09 Event time | Bounded named event questions preserve Calendar-only title and explicit period; fuzzy subject/assessment and numeric quiz identity controls | Ambiguity/updated event final answers across variations |
| 10 Reminder/event create | Existing native bridge/confirmation/persistence | Synthetic approved completion matrix; recurrence/calendar selection unsupported |
| 11 SFO arrival | Bounded traffic/current-location provider contract; private arrival boundary preserves unresolved/compound requests for clarification; exact SFO/address/ISO/buffer bindings offer only checked travel read | Actual native provider integration; default provider unavailable, interface alone is not completion |
| 12 Draft/send/schedule | Existing grounded workflows and durable approval-bound effects; recipient-before-channel drafts; source/dispatch dates separated; ambiguous/nonexistent DST clocks reject before queue/Contacts | Cross-source composition qualification, revised recipient approval tests; scheduled threaded replies unsupported |
| 13 Unsubscribe | Truthful sender/account-bound unverified candidate preparation; no false success | Actual verified unsubscribe provider and historical-open evidence unavailable |
| 14 Files | Extension/debug-filename-date grouping, content-bound previews, protected derived paths and atomic no-replace moves pass disposable filesystem tests; late source replacement reports unknown | Exact approved bytes require stable source entries through execution; full workflow grading, semantic content categorization and durable crash recovery remain unsupported |
| 15 Personal knowledge/followups | Explicit knowledge routes precede Notes; bounded saved notes, style examples and inert follow-up candidates; exact cached source IDs and editable revisions; actual synthetic loop checks enforce prior reads, duplicate-effect guards and existing policy | Broad source indexing, automatic preparation and context/style-guided draft qualification remain incomplete; Mail imports now require one immutable eligible cache generation; cross-source draft qualification remains pending |
| 16 Meeting | Checked private proposals use real event ends, exact duration and coherent fresh snapshots; bearer token remains host-only behind a turn-local one-use inert model reference; interactive approval precedes refreshed conflict/reference checks and strict native receipt | Actual native creation qualification and attendee invitation provider; generic meetings cannot silently become private blocks or invitations |
| 17 Fuzzy test time | Bounded subject typo/test-exam synonyms; quiz/midterm/final distinctions; multiple identities retained | Natural request binding and end-to-end ambiguity/answer tests |
| 18 Unread catchup | Actual unread Messages filtering; unknown-state/partial coverage; unread+date email intersection; shared basic direct reads | All qualified scope bindings and complete grounded catchup grading |
| 19 Availability message | Production delivery selects checked fresh/coherent find_free_time through a shared source contract; complete personally owned expression preserves periods/dayparts/integer-hour limits; stale/unknown-end/unsupported scope/denied preview blocks delivery | Empty availability still fails closed because the string result lacks a host-owned completion receipt. Half-hour bounds, multiple ranges and arbitrary conditions clarify. Local-model/native end-to-end qualification pending |
| 20 Pending actions | Bounded recorded-status history, exact-ID full-body inspection, atomic cancel/claim and truthful result classification; history-aware routing | End-to-end status answers and scheduler/native lost-receipt behavior; app acceptance cannot establish recipient delivery |

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
- Verified no-opening availability cannot yet be delivered by this executor:
  `no_match` remains non-success. Never treat arbitrary "No gaps" text as proof
  of fresh complete Calendar evidence. A separate host-owned receipt proposal
  is required before changing that result contract.
- A default availability window is 09:00–18:00; its result labels that window.
  Explicit integer-hour `after`/`before` bounds use the stated hour through
  midnight/from midnight. Unsupported combinations do not broaden the read.
- This candidate does not implement the separately planned Intel/GX10/Tailscale
  remote-only runtime; startup, authentication, packaging and endpoint changes
  for that milestone remain outside this diff.

See CONTRACT.md for fixture and observation format. Use the benchmark runner's
validate/routes/grade modes explicitly; grade accepts externally supplied traces
and does not itself prove their execution provenance.

## Current development base

Follow-up work starts from Wisp_Hackathon root commit
`d20f834d6d3f7e15a36daf6228c722a088a4c40f`. Prior source checkpoint
`c220e4a4c6173fe37e3fa62c9945ca7b76b563f1` remains preserved separately.
Dirty-worktree test runs are development evidence, not exact committed-head
qualification. The original Catch PR's required CI failed on five fixed-clock
fixtures; the failures were reproduced under UTC and repaired here by freezing
the test store clock. Production expiry and all assertions remain unchanged.
UTC and Pacific focused regressions pass; fresh committed-head CI is pending.

## Regression repair evidence

The first frozen PR3 candidate `0bb920222a364066e047db091a40eec41145a390`
failed its isolated full Python run: 189 of 198 gates passed, nine failed,
27,172 assertions passed and 20 failed. One gate supplied an incomplete count;
`counts_complete=false` is retained. That commit and its report are preserved.

The successor repairs arrival aliases, ordinary Calendar scope/context isolation,
exact weekend ranges, and public-weather voice classification. Explicit knowledge
instructions now remain separate from Apple Notes and from commands inside their
authored text. Edit/delete require the selected record read; current revision,
trusted request and existing mutation policy remain host checks. Authored text
preserves case, CRLF and trailing whitespace.

Actual synthetic loop tests reproduced failed-read deletion and changed-argument
repeat dispatch before the three knowledge mutation names joined the existing
effect guards. After the change, 83 focused knowledge cases pass, including
ordering, changed-argument duplicates, confirmation refusal, view-only denial,
missing records, stale revisions and stored-command isolation. These are fake
model traces with isolated storage; they do not qualify real model behavior.
Source-import instructions still require canonical single-space kind labels.
An empty saved-record read does not prove a record exists; the host refuses a
missing-ID mutation even if the model tries it after that read.
Fresh committed-head full checks, required CI and independent review remain
necessary. Priority body evidence/ranking and all listed native/provider gaps
remain open.

## Knowledge entrypoint repair

Frozen `8b6ec0e1341264ab56b61f1f9544a3de16cfbc03` passed all 198 offline
gates, with 27,298 reported passing assertions, zero failures and 155 skips.
One legacy unittest count remained unparsed (`counts_complete=false`). Distinct
scoped synthetic QA passed 498 unique cases. Independent source audit still
returned **BLOCK**, finding `W20KNOWLEDGEENTRY01`: a knowledge-note body such as
`Delete all reminders.` reached the earlier typed Reminder compiler before
knowledge routing. Confirmation remained enforced; no real deletion was observed.

Two isolated actual-handler regressions reproduced that interception with empty
and populated Reminder stores. The wrong destructive preview was refused by the
fixture. Those failures and the frozen commit's reports remain preserved.

The repair uses one pure knowledge-envelope grammar at the production entry
boundary and in routing. Complete and malformed addressed knowledge requests
skip earlier news, task, workflow and structured-read interpretation. All text
after a valid save/edit header's newline remains literal body data, including
later lines that look like commands. Stored task/workflow revisions and active
skill state remain intact. The host suppresses automatic skill context for this
turn, including tool-free clarification; ordinary turns keep the default skill
behavior. Credential redaction remains before parsing, and mutation policy,
confirmation, current-user provenance and exact argument checks still apply.

The expanded development suite passes 132 knowledge cases, including four
in-process HTTP `/agent` and `/agent/approve` requests, exact LF/CRLF/trailing
whitespace, authored Reminder/outbound/skill commands, malformed requests,
credential redaction, denial/view-only controls and ordinary Reminder/skill
positive controls. Models, native sinks and data are synthetic. Fresh committed
head full checks, required CI, independent audit and distinct specialist QA are
still required; the prior passes do not qualify this repair or all 20 workflows.

The next frozen revision, `b7012e5143f9ee2db0733d1d849ff4522c85b3e4`, also
passed all 198 offline gates (27,347 reported passes, zero failures, 155 skips,
one unparsed legacy count). Independent audit blocked it on
`W20KNOWLEDGEENTRY02`: an invalid Email/chat or Messages/account source-import
pairing returned no knowledge envelope, allowing an authored title to reach
Reminder parsing. Four actual HTTP regressions reproduced that failure with
empty and populated Reminder stores; the fixtures refused unintended previews.

The successor separates addressed import recognition from accepted import
authority. An invalid full import, or an incomplete Email/Messages import with
an explicit unquoted knowledge destination before its title, receives an empty
clarification envelope. Quoted subject text and incidental knowledge words do
not establish that destination. Exact accepted import grammar, source/container
validation, source identities, policy and approval remain unchanged. No main,
loop or task-compiler change is needed for this repair.

Expanded synthetic HTTP tests cover incomplete headers and trailing actions,
unchanged task/workflow/skill state, valid immutable Mail and normalized Messages
evidence, denial/view-only policy, stale/unavailable Mail publications and
current-request bindings that replace changed model arguments before approval.
Intermediate fixture mistakes (SSE event naming and expecting binding rejection
instead of exact host replacement) are preserved with their corrected runs.
The expanded suite passes 179 cases, including the prior 132 unchanged cases;
the focused cross-suite passes 14 files including that suite. These are
development results.
Fresh committed-head full checks, CI, audit and distinct QA remain necessary.

Frozen `dc07e1c2406ef33d5cbdcdacbe0d6b5235a23648` passed all 198 offline
gates (27,394 reported passes, zero failures, 155 skips, one unparsed legacy
count). Distinct isolated QA passed 311 checks. Independent audit still returned
**BLOCK** for residual `W20KNOWLEDGEENTRY02`: unsupported source wording, polite
direct requests and `titled` inside opaque IDs escaped the incomplete-request
recognizer. Eight actual HTTP cases reproduced the four residual variants over
empty and populated Reminder stores with unrelated pending state.

The next repair has one bounded clarification-only recognizer before the full
category check. It accepts optional Please and Can/Could/Would-you wrappers,
direct knowledge/style/follow-up category attempts, or Save/Store/Remember/Import
headers with an explicit unquoted `as` category destination. Unsupported source
descriptors, partial kind labels and immediately quoted kind labels clarify;
they acquire no tools or import authority. Accepted executable grammar and
bindings remain unchanged. Header roles distinguish source/container data from
title fields, including opaque IDs equal to `titled` or `in`. A quoted whole
subject cannot establish the destination, nor can text after a pre-destination
title or body delimiter. Filename punctuation does not become a category label.

The ambiguity policy preserves ordinary source-title requests such as
`Save email source-1 titled as a knowledge note` and
`Save email titled as a knowledge note` on their existing route (`None`). The
second form could also mean an incomplete import with ID `titled`; without a
structural `in account/chat` field it remains outside this bounded knowledge
attempt grammar. This is not a guarantee for arbitrary natural language or an
isolation fix for all ordinary Mail title/body requests.

Development tests pass 565 cases, retaining all prior 179 cases unchanged and
adding 386 cases, including 47 actual in-process HTTP cases. These cover pending
state preservation, zero other-source reads, hostile model calls, ordinary
source/title/filename controls and six valid immutable synthetic imports with
opaque source/account/chat IDs. A helper found three additional malformed field
variants before freeze; six failing HTTP cases were preserved and repaired.
Intermediate event-name assertion mistakes and a malformed pytest selector are
also retained. These results do not qualify the next committed head; fresh full
checks, required CI, independent audit and distinct QA remain required.

## Family 15 reference scope

The [Sentient OS product page](https://sentient-os.ai/) describes selected local
source analysis, editable personal knowledge, writing-style examples, contextual
drafts and proactive preparation. These are the relevant non-vision capabilities
for Wisp. This checkpoint does not implement their complete combination.

## Model evaluation

No Workflow20 model run or latency qualification has occurred. The routing
diagnostic freezes synthetic domain context and includes the earlier
`compile_read` entrypoint; it does not replay typed workflows, earlier tool
results or approvals. Cases without prescribed tool groups are unmeasured,
not positive routing evidence. Authentication and watchdog clocks must remain
real in a future model harness; the route diagnostic's frozen clock is not
an inference guard. Missing unsubscribe/invitation/traffic capabilities must
remain unsupported in synthetic model runs rather than receive fake success.
