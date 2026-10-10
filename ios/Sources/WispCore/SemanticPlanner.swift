import Foundation

public struct SemanticPlan: Sendable {
    public let family: WorkflowFamily
    public let question: String
    public let sources: [SourceKind]
    public let account: String?
    public let range: DateInterval?
}
public struct SemanticPlanner: Sendable {
    public init() {}
    public func plan(_ turns: [String], workspace: SemanticWorkspace) -> SemanticPlan? {
        guard let last = turns.last, last.utf8.count <= 4000, turns.count <= 20 else { return nil }
        let question = SemanticText.visibleRequest(last)
        let text = SemanticText.normalized(question), words = Set(SemanticText.words(text))
        guard !text.isEmpty else { return nil }
        func has(_ alternatives: [String]) -> Bool { alternatives.contains { (" " + text + " ").contains(" " + SemanticText.normalized($0) + " ") } }
        let family: WorkflowFamily
        if has(["unspecified", "what details", "quoted example"]) { return nil }
        if has(["unsubscribe", "subscription"]) { family = .unsubscribe }
        else if has(["organize", "categorize", "move files", "debug files"]) { family = .files }
        else if has(["cancel", "pending", "queued actions", "scheduled sends"]) { family = .pending }
        else if has(["remind me", "add a reminder", "create a reminder", "put an event", "create an event", "add an event", "calendar event for"]) { family = .create }
        else if has(["schedule a meeting", "arrange a meeting", "book a meeting"]) { family = .meeting }
        else if has(["airport", "sfo", "traffic", "route", "maps"]) { family = .trip }
        else if has(["send", "draft", "reply", "tell them", "tell him", "tell her"]) { family = has(["busy", "free", "availability"]) ? .availability : .communication }
        else if has(["unread", "not read", "havent read", "catch up", "catchup"]) { family = .unread }
        else if has(["grocery", "groceries", "shopping", "buy", "costco", "checked items"]) { family = .groceries }
        else if has(["weather", "forecast", "rain", "temperature"]) { family = .weather }
        else if has(["daily", "my day", "day looking", "this morning", "briefing", "walk me through today", "rundown for today"]) && !has(["said", "say", "told", "tell me", "text"]) { family = .daily }
        else if has(["priority", "priorities", "focus", "work on", "tackle", "needs attention", "need to do", "due at work"]) { family = .priorities }
        else if has(["thread", "group", "chain", "chat", "what changed", "what did we decide"]) { family = .thread }
        else if has(["said", "say", "told", "tell me", "texted", "get back", "hear from", "tell us"]) { family = .contact }
        else if has(["test", "exam", "quiz", "midterm", "mid term", "assessment", "final"]) && has(["when", "time", "day", "next", "have"]) { family = .fuzzyEvent }
        else if has(["when", "what time", "start"]) { family = .event }
        else if has(["calendar", "schedule", "today", "tomorrow", "tommorow", "tmrow", "this week", "next week", "this month"]) && !has(["mail", "email", "emails", "message", "messages", "texts", "notes", "inbox"]) { family = .schedule }
        else if has(["knowledge", "memory", "project notes", "remember"]) { family = .knowledge }
        else if has(["overview", "summary", "summarize", "mail", "messages", "texts", "inbox", "calendar"]) { family = .overview }
        else { return nil }
        var sources: [SourceKind] = []
        let aliases: [(SourceKind, [String])] = [(.email,["email","emails","mail","inbox"]), (.messages,["messages","message","texts","text","imessage"]), (.calendar,["calendar","calender","events"]), (.notes,["notes","note"]), (.reminders,["reminders","reminder"])]
        for (kind, names) in aliases where names.contains(where: words.contains) { sources.append(kind) }
        if has(["skip calendar", "without calendar", "no calendar"]) { sources.removeAll { $0 == .calendar } }
        if has(["skip mail", "without email", "no email"]) { sources.removeAll { $0 == .email } }
        if has(["skip messages", "without texts", "no messages"]) { sources.removeAll { $0 == .messages } }
        switch family {
        case .daily: sources = [.email,.messages,.calendar,.reminders]
        case .schedule,.event,.fuzzyEvent: sources = [.calendar]
        case .groceries: sources = sources.filter { [.notes,.reminders].contains($0) }; if sources.isEmpty { sources = [.notes,.reminders] }
        case .contact,.thread,.unread: sources = sources.filter { [.email,.messages].contains($0) }; if sources.isEmpty { sources = [.email,.messages] }
        case .weather: sources = [.weather]
        case .priorities: sources = [.email,.messages,.calendar,.notes,.reminders]
        case .knowledge: sources = [.memory,.notes]
        case .pending: sources = [.queue]
        default: if sources.isEmpty { sources = [.email,.messages,.calendar] }
        }
        if has(["skip calendar", "without calendar", "no calendar"]) { sources.removeAll { $0 == .calendar } }
        if has(["skip mail", "without email", "no email"]) { sources.removeAll { $0 == .email } }
        if has(["skip messages", "without texts", "no messages"]) { sources.removeAll { $0 == .messages } }
        let account = ["work", "personal", "school"].first { words.contains($0) }
        return .init(family: family, question: question, sources: sources, account: account,
                     range: SemanticDates.range(question: question, clock: workspace.clock, timezone: workspace.timezone, defaultToday: [.daily,.schedule].contains(family)))
    }
}
