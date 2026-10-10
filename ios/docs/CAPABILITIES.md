# iPhone capability matrix

Prototype checkpoint on October 10, 2026. Deterministic queries run over supplied
synthetic/imported records; native sources and models remain disconnected.

| Workflow families | Current bounded behavior | Incomplete capability |
| --- | --- | --- |
| 01 overview, 02 daily | Source quotes, IDs, local date filters and coverage | Native inboxes and semantic synthesis |
| 03 calendar ranges | Today/tomorrow/yesterday, weekdays, this/next week/month, one ISO date, timezone/DST overlap | Custom ranges and richer temporal language |
| 04 weather | Verify envelope/forecast city and canonical region metadata for one day | Live weather, broad location resolution, region aliases |
| 05 priorities | Explicit requests and structured due dates | Inferred ranking, effort and estimates |
| 06 contact, 07 thread | Sender identity ambiguity, full-name/address selection, user-history pronouns, literal topics, stable threads and chronological quotes | Broad identity linking and synthesized final decisions |
| 08 groceries | Structured shopping items, completed-item exclusion, name dedupe and quantity conflicts | Plain-text completion inference and native Notes |
| 09 event time | Title matching, date filters and ambiguous-title clarification | Rich temporal relations and broad semantic aliases |
| 10 reminder/event create | Clarification; exact user-entered form preview | Native creation and receipts |
| 11 trip | Unsupported, zero effects | Location, traffic, arrival planning and Maps handoff |
| 12 communication | Clarification; exact user-entered form preview | Grounded drafting, composers, sends and scheduled delivery |
| 13 unsubscribe | Unsupported, zero effects | Engagement history and provider integration |
| 14 files | Unsupported, zero effects | Scoped files, approved reversible moves and receipts |
| 15 knowledge | Imported memory/note quotes | Persistent editable index and richer retrieval |
| 16 meeting | Clarification, no action | Contact resolution, scheduling, invitations |
| 17 fuzzy test | Bounded typo matching, assessment-kind filtering, next active subject match | Model semantics and broader course aliases |
| 18 unread | Explicit true only; unknown state excluded and disclosed | Native synchronization and importance ranking |
| 19 availability reply | Clarification, no action | Interval reasoning, grounded draft and approved send |
| 20 pending | Unsupported, zero effects | Durable queue and cancellation receipts |

The production adapter ignores the benchmark's gold family and reference oracle.
Canonical source-field claims are emitted separately from arbitrary v1 oracle fact
aliases; the bridge is unavailable, so no twenty-workflow completion claim follows
from status counts or source-provenance checks. Preview confirmation performs no
native or provider effect. All actual effect/approval arrays stay empty.

## Platform boundaries

- **Messages/Mail:** baseline uses selected paste/import. MessageUI offers
  user-operated composers, not a general inbox reader; composition does not prove
  delivery. No general native Apple Mail inbox API was established by the reviewed
  public docs. Specialized TelephonyMessagingKit carrier messaging requires the
  default-app role, entitlement and EU eligibility; it is not general iMessage
  archive access and is outside this port.
  [MessageUI](https://developer.apple.com/documentation/messageui),
  [TelephonyMessagingKit](https://developer.apple.com/documentation/TelephonyMessagingKit).
- **Calendar/Reminders:** EventKit reads require full access; there is no read-only
  permission. Write-only calendar authorization cannot read events. Included
  request methods are not connected to the app UI. Source methods never save
  events or reminders.
  [Event store access](https://developer.apple.com/documentation/eventkit/accessing-the-event-store).
- **Contacts:** permission state includes limited access on iOS 18+. Limited data
  cannot establish a complete directory. Contact notes are excluded; no native
  contact lookup is currently connected.
  [Contacts access](https://developer.apple.com/documentation/contacts/accessing-the-contact-store).
- **Scheduling:** notifications remind users; they do not send messages. Background
  refresh runs at system-chosen times and cannot promise exact-time delivery.
  Neither facility is configured in this app.
  [Background strategies](https://developer.apple.com/documentation/backgroundtasks/choosing-background-strategies-for-your-app),
  [Local notifications](https://developer.apple.com/documentation/usernotifications/scheduling-a-notification-locally-from-your-app).
- **Maps/Weather:** live directions and forecasts require separately scoped service
  calls, WeatherKit capability/attribution, and location permission when needed.
  No provider calls or location prompts are made here.
  [Directions](https://developer.apple.com/documentation/mapkit/mkdirections),
  [WeatherKit](https://developer.apple.com/weatherkit/).
- **Inference:** `SystemLanguageModel.default` is Apple's on-device model; the
  broader FoundationModels framework also has provider/cloud functionality, so
  framework import alone does not establish locality. Device/region/Apple
  Intelligence/model readiness affect availability. No automatic activation,
  model download, load, inference, latency or thermal measurement occurred.
  [SystemLanguageModel](https://developer.apple.com/documentation/foundationmodels/systemlanguagemodel).
- **Import:** explicit paste and balanced security-scoped file access; a share
  extension would be a separate target. Text import is capped at 64 KiB and stays
  in memory. UI layout, paste prompt behavior and revocation still require actual
  simulator/device runtime QA.
  [Paste control](https://developer.apple.com/documentation/uikit/uipastecontrol),
  [File access](https://developer.apple.com/documentation/uikit/providing-access-to-directories).

## Readiness limits

Unsigned simulator compilation covers SwiftUI, iOS API availability and framework
linkage for arm64/x86_64. It does not prove a signed device build, installation,
permissions, UI interaction, inference quality, memory, thermals, speed or battery
behavior. No simulator was launched in this checkpoint; physical-device installation remains untested. Native
permission adapters need isolated specialist QA before integration. Independent
release review and any required QA must bind the exact frozen candidate SHA.
