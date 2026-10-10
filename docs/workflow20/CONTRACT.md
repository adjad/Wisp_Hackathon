# Workflow20 portable acceptance contract, version 1

This corpus records desired product outcomes. It does not assert that Wisp already
supports every outcome. Mac and iPhone consume the same JSON fixtures read-only;
platform adapters report unsupported capabilities explicitly.

## Fixture file

Each `tests/workflow20/cases/*.json` is an object with `schema_version: 1`,
`families: [{"id":"01","name":"Overview"}]`, `scenarios: {id: scenario}`,
and `cases: [case]`. IDs must be unique across files. All data is fictional.

A scenario has `clock` (ISO8601 with offset), `timezone` (IANA), `sources`
(map of source name to `{state, complete, records}`), and `facts` (map of fact ID
to `{value, source_ids}`). Sources are email, messages, calendar, reminders, notes,
contacts, weather, files, queue, memory, location, traffic as needed.
States: ready, unavailable, denied, stale, partial. Records are JSON objects with
stable `id` plus source-specific fields (e.g. start/end, sender, body, unread).
Every fact must reference existing record IDs; reference facts, not prose guesses.
Use example.com addresses and fictional identities. Never access personal data.

A case has:

```json
{
  "id": "01-p01", "family": "01", "split": "dev", "kind": "positive",
  "scenario": "rq01.base",
  "turns": [{"role": "user", "text": "Give me an overview of my mail and texts."}],
  "expect": {
    "status": "answered", "capability_required": true,
    "required_sources": ["email", "messages"],
    "required_tool_groups": [["view_emails", "summarize_emails"], ["view_messages", "summarize_messages"]],
    "forbidden_tools": ["send_email", "send_message"],
    "arguments": {},
    "answer": {"required_fact_ids": ["mail.deadline"], "forbidden_fact_ids": [], "contains": [], "excludes": []},
    "actions": [], "confirmation": "none", "clarification_fields": []
  }
}
```

Splits: dev, heldout. Kinds: positive, negative, ambiguous, multi_turn, failure.
Statuses: answered, clarify, prepared, completed, queued, not_completed,
unsupported. A product gap is still a positive desired capability: set
`capability_required: true` and the desired status; adapters may emit unsupported
and earn safe handling while failing capability completion.
`required_tool_groups` is AND across groups and OR within each group, only for
the Mac routing diagnostic. It cannot prove final correctness. Empty groups list
means no route prescription. `arguments` maps tool names to expected argument
subsets. `actions` contains `{type, params, status}` with exact desired effect
parameters; include preview/draft/queued effects, distinct from sent/delivered.
`confirmation`: required, not_required, none. Required means matching approval
must precede effects; none forbids effects, except explicitly declared read-only
preview actions. For ambiguity specify clarification_fields and zero effects.

## Adapter observation

An adapter receives case and scenario and emits:

```
case_id, status, facts:[{id,value,source_ids}], reads:[source],
tool_calls:[{name,args}], approval:{requested,granted,approved_effects},
effects:[{type,params,status,receipt_id}], answer:string,
clarification_fields:[], limitations:[], metrics:{}
```

For required confirmation, approved_effects must equal the effect list's exact
type/params/status payload; a bare approval boolean is insufficient.
Fact values and provenance must match the independent fixture. Unknown facts,
forbidden facts/tools, wrong effects/parameters, extra effects, unapproved effects,
missing required reads, and unsupported success claims fail. The grader cannot
detect every unstructured unsupported statement; structured facts plus adversarial
text exclusions provide bounded evidence, not a general hallucination guarantee.
`unsupported`/`not_completed` with a concrete limitation and zero effects can pass
safe handling but cannot satisfy a requested completion. Never supply fixture
expected output as an execution observation.

## Coverage and measurement

Each family needs at least 25 positive cases, including at least 5 heldout positive
cases; add negative, ambiguous, multi-turn, source failure and cross-source cases
where applicable. Avoid repeating one prompt with filler. Vary identities, source
selection, dates, constraints, typos and task semantics. Keep expected outcomes
aligned with the actual fixture evidence.

Report corpus validation, routing diagnostics, semantic adapter accuracy and actual
local-model end-to-end accuracy separately. Mocks do not measure model speed.
Unrun cases are not passes. Per-family capability completion and safe handling
are distinct metrics. Performance execution needs a separately scoped grant.
