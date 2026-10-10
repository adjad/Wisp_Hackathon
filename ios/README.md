# Wisp iPhone prototype

Standalone SwiftUI app for bounded queries over fictional or explicitly imported
records. The Workspace tab accepts natural-language questions and displays answers,
source quotes/IDs, missing metadata and partial coverage. The Action preview tab
builds immutable reminder, event or message payloads from explicit form fields;
confirmation acknowledges only the local preview. Nothing is sent or saved to a
native app. No Mac server, account or model is needed.

This checkpoint is not twenty-workflow parity. Native accounts, AI inference,
persistent memory, background scheduling and external effects remain disconnected.
Read [capabilities](docs/CAPABILITIES.md) for supported behavior and limitations.

## Run on your iPhone

Follow [device setup and test checklist](docs/RUN_ON_IPHONE.md). Use a separate copy
for your signing settings. Deployment target is iOS 17; the optional disabled
Foundation Models adapter requires the newer SDK framework when compiled. This
checkpoint was compiled with Xcode 27 / iOS 27 SDK, for both simulator architectures.
No signed physical-device run has been performed.

## Try the demo

The clock is deliberately fixed at October 10, 2026, in America/Los_Angeles:

- `What is on my calendar today?`
- `What did Mira say in messages?`
- `Summarize Garden volunteers messages thread`
- `What groceries should I buy from notes?`
- `When is my astronomy test?`
- `Unread email`
- `Daily briefing`

Replies preserve source wording; they are deterministic selections, not model
summaries. Thread messages are shown chronologically, including corrections.
Ambiguous contacts/threads/events ask for details. Unread state must be explicit.
Shopping lists use structured open/checked metadata, deduplicate names and disclose
quantity conflicts. Date filters use source timezone, half-open overlap and DST;
today/tomorrow/yesterday, weekdays, this/next week/month and one ISO date are
supported. Modified weekdays and conflicting/custom ranges clarify rather than
silently narrowing. Unknown dates are excluded from date-scoped queries. Priority
views select explicit requests and due dates without estimating effort.

Plain-text paste/import has no inferred sender, dates or unread state. Structured
JSON carries explicit metadata; see [import-example.json](docs/import-example.json).
Explicit source mentions restrict reads; mixed/excluded accounts and ambiguous
source restrictions clarify before reading. Follow-ups must restate source/account
scope when identity reuse could broaden it. Both imports replace the current workspace, stay in memory and are capped at 64 KiB.
There is no account sync, persistence or share extension. Source text is data and
cannot invoke an action. Reset discards imported records.

## Offline verification

From repository root:

```sh
swift test --package-path ios --scratch-path /private/tmp/wisp-iphone-core
xcodebuild -project ios/WispPhone.xcodeproj -scheme WispPhone \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /private/tmp/wisp-iphone-app CODE_SIGNING_ALLOWED=NO build
```

From a clean committed checkout, capture exact-head evidence with:

```sh
python3 ios/scripts/verify.py --expected-sha <full-sha> \
  --artifacts <outside-repo-directory> --fixtures <shared-workflow20-cases-directory>
```

The verifier does not launch a simulator, install an app, request permissions or
run a model. `scripts/generate_project.py` regenerates the Xcode project after
Swift source files are added or removed, using only Python's standard library.

## Shared portable evaluation

The CLI consumes Mac-owned fixture files read-only:

```sh
swift run --package-path ios --scratch-path /private/tmp/wisp-iphone-core \
  workflow20-ios /path/to/shared/cases/actions.json /path/to/shared/cases/read_query.json
```

The adapter uses the same engine as the app. It routes from user turns and records,
ignores gold family during execution, and does not decode scenario reference
`facts` or case `expect`. Observations contain actual status, answer, reads and
canonical source-field claims under `metrics.source_claims`, with zero effects,
approvals and inference. The old foundation adapter remains for plumbing tests.

Shared v1 grading requires arbitrary oracle fact aliases that are absent from
production records. They are not fabricated. `facts` remains empty in runtime output. The Mac-owned
independent evaluator can map strictly equivalent whole JSON values and exact
provenance from canonical claims, after validating them against actual records. Status counts, route agreement and the separate
source-value/provenance audit are **not semantic benchmark passes**. The shared
grader's completion result must remain visible, including failures. Its strict
structured assertions do not establish arbitrary free-form answer quality. No model
accuracy, latency or physical-device performance has been measured.

## Optional local model boundary

`AppleLocalInference` selects `SystemLanguageModel.default`, checks availability,
exposes no tools/cloud fallback, caps input and validates whole excerpts/IDs. It
cannot create action parameters. Its scope defaults to nil; the app does not
instantiate it. Actual on-device feasibility and quality remain unmeasured.
