import Foundation

public struct SemanticPlan: Sendable {
    public let family: WorkflowFamily
    public let question: String
    public let sources: [SourceKind]
    public let account: String?
    public let range: DateInterval?
    public let clarificationFields: [String]
    public let clarificationMessage: String?
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
        else if has(["availability"]) { family = .availability }
        else if has(["schedule", "scheduled", "queue"]) && has(["text", "texts", "message", "messages", "email", "emails", "reply"]) { family = .communication }
        else if has(["text", "message"]) && !has(["text messages"]) { family = .communication }
        else if text.hasPrefix("email ") || has(["can you email", "could you email", "would you email", "please email", "email to"]) { family = .communication }
        else if has(["airport", "sfo", "traffic", "route", "maps"]) { family = .trip }
        else if has(["send", "draft", "reply", "tell them", "tell him", "tell her"]) { family = has(["busy", "free", "availability"]) ? .availability : .communication }
        else if has(["unread", "not read", "havent read", "catch up", "catchup"]) { family = .unread }
        else if has(["grocery", "groceries", "shopping", "buy", "costco", "checked items"]) { family = .groceries }
        else if has(["weather", "forecast", "rain", "temperature"]) { family = .weather }
        else if has(["daily", "my day", "day looking", "briefing", "walk me through today", "rundown for today"]) && !has(["said", "say", "told", "tell me", "text"]) { family = .daily }
        else if has(["priority", "priorities", "focus", "work on", "tackle", "needs attention", "needs my attention", "action item", "action items", "need to do", "due at work"]) { family = .priorities }
        else if has(["thread", "group", "chain", "chat", "recap", "what changed", "what did we decide"]) { family = .thread }
        else if has(["said", "say", "told", "tell me", "texted", "get back", "hear from", "tell us"]) { family = .contact }
        else if has(["test", "exam", "quiz", "midterm", "mid term", "assessment", "final"]) && has(["when", "time", "day", "next", "have"]) { family = .fuzzyEvent }
        else if has(["when", "what time", "start"]) { family = .event }
        else if has(["calendar", "schedule", "today", "tomorrow", "tommorow", "tmrow", "this week", "next week", "this month"]) && !has(["mail", "email", "emails", "message", "messages", "texts", "notes", "inbox"]) { family = .schedule }
        else if has(["knowledge", "memory", "project notes", "remember"]) { family = .knowledge }
        else if has(["overview", "summary", "summarize", "mail", "messages", "texts", "inbox", "calendar"]) { family = .overview }
        else { return nil }
        let aliases: [(SourceKind, [String])] = [(.email,["email","emails","mail","inbox"]), (.messages,["messages","message","texts","text","imessage"]), (.calendar,["calendar","calendars","calender","events"]), (.notes,["notes","note"]), (.reminders,["reminders","reminder"]), (.memory,["memory"]), (.weather,["weather","forecast"]), (.queue,["queue"]), (.contacts,["contacts"]), (.files,["files"]), (.location,["location"]), (.traffic,["traffic"])]
        let mentioned = aliases.filter { $0.1.contains(where: words.contains) }.map(\.0)
        var excluded = Set<SourceKind>()
        for (kind, names) in aliases {
            for name in names {
                let pattern = "\\b(without|skip|exclude|excluding|except|not|no|avoid|omit|ignore|leave out)\\s+((my|the|any|from|using|on|for)\\s+)*" + name + "\\b"
                if text.range(of: pattern, options: .regularExpression) != nil { excluded.insert(kind) }
            }
        }
        let defaults: [SourceKind]
        switch family {
        case .daily: defaults = [.email,.messages,.calendar,.reminders]
        case .schedule,.event,.fuzzyEvent: defaults = [.calendar]
        case .groceries: defaults = [.notes,.reminders]
        case .contact,.thread,.unread: defaults = [.email,.messages]
        case .weather: defaults = [.weather]
        case .priorities: defaults = [.email,.messages,.calendar,.notes,.reminders]
        case .knowledge: defaults = [.memory,.notes]
        case .pending: defaults = [.queue]
        default: defaults = [.email,.messages,.calendar]
        }
        let allowed: [SourceKind] = family == .overview ? [.email,.messages,.calendar,.notes,.reminders,.memory] : defaults
        let positive = mentioned.filter { !excluded.contains($0) }
        var sources = (positive.isEmpty ? defaults : positive.filter(allowed.contains)).filter { !excluded.contains($0) }
        var fields: [String] = []
        var message: String?
        let accounts = ["work", "personal", "school"].filter(words.contains)
        let negatedAccount = accounts.contains { account in
            text.range(of: "\\b(not|no|without|except|excluding|skip)\\s+(my\\s+|the\\s+)?" + account + "\\b", options: .regularExpression) != nil
        }
        if accounts.count > 1 || negatedAccount || (!accounts.isEmpty && ["not", "dont", "never", "avoid", "except", "excluding", "without", "skip", "no"].contains(where: words.contains)) {
            fields = ["account"]; message = "Please name one account to include. Mixed or excluded account requests need clarification."
        } else if has(["do not", "dont", "never", "stop"]) {
            fields = ["scope"]; message = "Please state the read request and included sources explicitly. No sources were read."
        } else if (words.contains("only") && positive.count != 1) || sources.isEmpty || (!excluded.isEmpty && mentioned.count > 1) {
            fields = ["source"]; message = "Please name the sources to include explicitly; this source restriction needs clarification."
        }
        if message == nil, [.contact, .thread, .unread].contains(family), turns.count > 1,
           ["he", "she", "them", "him", "her"].contains(where: words.contains) {
            let previousText = SemanticText.visibleRequest(turns[turns.count - 2])
            let previousWords = Set(SemanticText.words(previousText))
            let previousAccounts = ["work", "personal", "school"].filter(previousWords.contains)
            if positive.isEmpty || (!previousAccounts.isEmpty && accounts.isEmpty) {
                fields = ["source", "account"]; message = "Please restate the contact, source and account for this follow-up. Earlier identity cannot expand the read scope."
            }
        }
        if message != nil { sources = [] } // Clarification cannot read broad defaults.
        return .init(family: family, question: question, sources: sources, account: accounts.first,
                     range: SemanticDates.range(question: question, clock: workspace.clock, timezone: workspace.timezone, defaultToday: [.daily,.schedule].contains(family)),
                     clarificationFields: fields, clarificationMessage: message)
    }
}
