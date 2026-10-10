import Foundation

/// Fictional, source-only records. No case IDs, oracle labels or expected answers are present.
public enum SemanticDemo {
    public static func workspace() -> SemanticWorkspace {
        let clock = SemanticDates.parse("2026-10-10T09:00:00-07:00")!
        func record(_ source: SourceKind, _ id: String, _ fields: [String: JSONValue]) -> SemanticRecord {
            var fields = fields; fields["id"] = .string(id); return .init(source: source, fields: fields)
        }
        let messages = [
            record(.messages, "demo-msg-1", ["sender": .string("Mira Chen <mira@example.invalid>"), "conversation": .string("Garden volunteers"), "thread_id": .string("garden"), "timestamp": .string("2026-10-10T08:10:00-07:00"), "body": .string("Let's meet at the east gate at 10."), "unread": .bool(false)]),
            record(.messages, "demo-msg-2", ["sender": .string("Mira Chen <mira@example.invalid>"), "conversation": .string("Garden volunteers"), "thread_id": .string("garden"), "timestamp": .string("2026-10-10T08:40:00-07:00"), "body": .string("Correction: west gate at 11. Bring gloves."), "unread": .bool(true)])]
        let calendar = [
            record(.calendar, "demo-cal-1", ["title": .string("Garden volunteering"), "start": .string("2026-10-10T11:00:00-07:00"), "end": .string("2026-10-10T12:00:00-07:00")]),
            record(.calendar, "demo-cal-2", ["title": .string("Astronomy midterm"), "start": .string("2026-10-14T13:30:00-07:00"), "end": .string("2026-10-14T15:00:00-07:00")])]
        let notes = [record(.notes, "demo-note-1", ["title": .string("Shopping list"), "items": .array([
            .object(["name": .string("Pears"), "quantity": .string("4"), "completed": .bool(false)]),
            .object(["name": .string("Tea"), "completed": .bool(true)]),
            .object(["name": .string("Oats"), "completed": .bool(false)])])])]
        let reminders = [record(.reminders, "demo-rem-1", ["title": .string("Return library book"), "due": .string("2026-10-10T17:00:00-07:00"), "completed": .bool(false)])]
        let email = [record(.email, "demo-mail-1", ["sender": .string("Dario Silva <dario@example.invalid>"), "subject": .string("Poster review"), "timestamp": .string("2026-10-10T08:30:00-07:00"), "body": .string("Please review the poster by Tuesday."), "unread": .bool(true)])]
        return .init(origin: .synthetic, clock: clock, timezone: TimeZone(identifier: "America/Los_Angeles")!,
                     sources: [.messages: .init(state: .ready, complete: true, records: messages), .calendar: .init(state: .ready, complete: true, records: calendar),
                               .notes: .init(state: .ready, complete: true, records: notes), .reminders: .init(state: .ready, complete: true, records: reminders),
                               .email: .init(state: .ready, complete: true, records: email)])
    }
}
