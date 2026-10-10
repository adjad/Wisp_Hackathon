# iPhone semantic checkpoint

Owner: 01a12778-56ee-74e0-81bb-18b7b906bd3a. Scope: ios/** only.
Checkout: /Users/adijain/Documents/Codex/2026-10-10/wisp-iphone-hackathon
Branch: codex/iphone-workflows
Base: d20f834d6d3f7e15a36daf6228c722a088a4c40f (single-root new repository).
The old foundation commit/evidence remains preserved in its original checkout;
no old ancestry is merged or published in this branch.

Implemented: shared deterministic planner/source-record engine used by app and
portable adapter; query UI; canonical source-field claims; contact/thread identity
ambiguity; local calendar/DST/date filters; bounded fuzzy event lookup; structured
shopping completion/dedupe/conflict handling; explicit unread state; conservative
weather location verification; in-memory structured/text import; exact typed
local action preview and confirmation. Reference oracle and gold family do not
control execution. No live account, permission, model or effect was invoked.

Pre-freeze tests: 55 Swift test functions PASS, including source/oracle mutation,
source denial, missing metadata, DST overlap, sender/address ambiguity, historical
thread corrections, unread uncertainty, shopping conflicts, forecast location
mismatch and immutable preview approval. Unsigned generic simulator build PASS.
A first test run caught a topic-filter error; regression repairs passed.

Shared 597-case observations and canonical provenance integrity are captured
outside the checkout. Source claims are not arbitrary v1 fact aliases; alias
mapping requires independent evaluator ownership. Shared semantic completion is
not qualified. A pre-freeze privacy-routing finding is recorded for the
Orchestrator to acknowledge this builder as sole repair owner before repair.
Status counts and source-value checks are not benchmark accuracy.

Final exact-head/CI/review evidence belongs in the external candidate handoff.
Native integration/build-target/privacy risks trigger independent Release Auditor
and specialist synthetic QA, registered by the Orchestrator for the same SHA.
Device instructions are prepared in RUN_ON_IPHONE.md; user testing is not a
substitute for these gates. No signed build, simulator interaction, physical-device
run, local AI measurement, release or main merge has occurred.

Root pulls /private/tmp/wisp-iphone-newroot-status-20261010.json. This status is a
mirror/request, never the authoritative ownership registry. No retries of rejected
outbound coordination sends. Shared Mac fixture/contract paths remain read-only.

Pending same-owner repair request also includes account negation/mixed-account
scope, exclusive source restrictions overridden by family defaults, conflicting
relative-date modifiers, non-Latin shopping-item dedupe, and explicit weather
region qualification. The read-only helper identified these before freeze. They
remain recorded limitations of this pre-review checkpoint; do not treat it as a
merge-ready or user-device-tested candidate. The Orchestrator must acknowledge
repair ownership before edits to these findings.
