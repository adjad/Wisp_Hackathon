import Foundation

/// Bounded deterministic execution over supplied records. No native APIs, model or oracle access.
public struct SemanticEngine: Sendable {
    public init() {}
    public func respond(turns: [String], in workspace: SemanticWorkspace) -> SemanticResult {
        guard let plan = SemanticPlanner().plan(turns, workspace: workspace) else {
            return SemanticResult(status: .clarify, answer: "Which source, person, topic or event should I look up?", clarificationFields: ["target"])
        }
        let family = plan.family
        if plan.question.range(of: #"\b\d{4}-\d{2}-\d{2}\b"#, options: .regularExpression) != nil && plan.range == nil {
            return SemanticResult(family: family, status: .clarify, answer: "Please provide a valid calendar date.", clarificationFields: ["date"])
        }
        let isoCount = plan.question.matches(of: /\b\d{4}-\d{2}-\d{2}\b/).count
        let weekdayCount = Set(SemanticText.words(plan.question)).intersection(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]).count
        if isoCount > 1 || weekdayCount > 1 {
            return SemanticResult(family: family, status: .clarify, answer: "Please use one date, this week, next week or this month. Custom date ranges are not supported yet.", clarificationFields: ["date_range"])
        }
        if plan.question.range(of: #"\b(on|in|for)\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b|\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return SemanticResult(family: family, status: .clarify, answer: "Please enter the date as YYYY-MM-DD.", clarificationFields: ["date"])
        }
        if [.create,.communication,.availability,.meeting].contains(family) { return preview(plan, workspace: workspace) }
        if [.trip,.unsubscribe,.files,.pending].contains(family) {
            return SemanticResult(family: family, status: .unsupported, answer: "",
                                  limitations: ["\(family.title) requires a separately connected provider or scoped native integration. No action was performed."])
        }
        var result = SemanticResult(family: family, status: .answered, answer: "")
        result.limitations.append(workspace.origin == .synthetic ? "Synthetic source data; no account was accessed." : "Only selected imported records are available; no live account was accessed.")
        var records: [SemanticRecord] = []
        var incomplete = false
        for kind in plan.sources {
            guard let source = workspace.sources[kind] else { result.limitations.append("\(kind.rawValue): not connected."); incomplete = true; continue }
            guard [.ready,.partial].contains(source.state) else { result.limitations.append("\(kind.rawValue): \(source.state.rawValue); excluded."); incomplete = true; continue }
            result.reads.append(kind)
            if !source.complete || source.state == .partial { incomplete = true; result.limitations.append("\(kind.rawValue): partial coverage.") }
            if plan.account != nil && source.records.contains(where: { $0.string("account").isEmpty }) {
                incomplete = true; result.limitations.append("\(kind.rawValue): records without an account label were excluded from the account filter.")
            }
            records += source.records.filter { record in
                !record.inactive && (plan.account == nil || record.string("account").lowercased() == plan.account)
            }
        }
        if result.reads.isEmpty { result.status = .unsupported; return result }
        if [.contact,.thread,.unread].contains(family) {
            let selection = selectIdentity(records, plan: plan, turns: turns)
            if !selection.ambiguities.isEmpty {
                result.status = .clarify; result.answer = "Which \(selection.field) do you mean: \(selection.ambiguities.joined(separator: ", "))?"
                result.clarificationFields = [selection.field]; return result
            }
            if family == .contact && selection.selected == nil {
                result.status = .clarify; result.answer = "Which contact do you mean?"; result.clarificationFields = ["contact"]; return result
            }
            if let selected = selection.selected { records = selected }
            else if family == .thread {
                result.status = .clarify; result.answer = "Which thread or group should I summarize?"; result.clarificationFields = ["thread"]; return result
            }
        }
        if family == .unread {
            if records.contains(where: { $0.fields["unread"]?.bool == nil }) {
                result.limitations.append("Unread state is unknown for some available records; those records are excluded."); incomplete = true
            }
            records = records.filter { $0.fields["unread"]?.bool == true }
        }
        if family == .event || family == .fuzzyEvent { return event(records, plan: plan, result: result, workspace: workspace, incomplete: incomplete) }
        if family == .groceries { return groceries(records, plan: plan, result: result, incomplete: incomplete) }
        if family == .weather { return weather(records, plan: plan, result: result, workspace: workspace, incomplete: incomplete) }
        if let range = plan.range {
            if records.contains(where: { $0.source == .calendar && $0.date("start") == nil }) {
                result.limitations.append("Some calendar records lack valid start dates; excluded from the date filter."); incomplete = true
            }
            records = records.filter { record in
                if record.source == .calendar { return SemanticDates.overlaps(record, range) }
                if record.source == .reminders, let due = record.date("due") { return due >= range.start && due < range.end }
                if let date = record.timestamp { return date >= range.start && date < range.end }
                return true // Unknown import dates remain explicitly unfiltered.
            }
            if records.contains(where: { $0.source != .calendar && $0.timestamp == nil && $0.date("due") == nil }) {
                result.limitations.append("Some records lack timestamps; their dates could not be filtered."); incomplete = true
            }
        }
        if family == .priorities {
            records = records.filter { record in
                record.source == .calendar || record.source == .reminders || ["priority","due","deadline","please","need"].contains { SemanticText.normalized(record.body + " " + record.title).contains($0) }
            }.sorted { left, right in
                let a = left.date("due") ?? left.date("start") ?? .distantFuture
                let b = right.date("due") ?? right.date("start") ?? .distantFuture
                return a == b ? left.id < right.id : a < b
            }
            result.limitations.append("Explicit requests and structured due dates are shown; inferred effort and priority weights are not available.")
        } else { records.sort { ($0.timestamp ?? .distantPast, $0.id) < ($1.timestamp ?? .distantPast, $1.id) } }
        var lines: [String] = []
        for record in records.prefix(50) {
            let field = !record.body.isEmpty ? (record.fields["body"] == nil ? "text" : "body") : record.fields["title"] != nil ? "title" : record.fields["subject"] != nil ? "subject" : "name"
            let text = record.fields[field]?.string ?? record.title
            let label = record.source == .calendar ? record.title : !record.sender.isEmpty ? record.sender : record.title
            var detail = text
            if let start = record.date("start") {
                detail = record.title + " — " + SemanticDates.display(start, timezone: workspace.timezone)
                addClaim(record, "start", to: &result)
            }
            if let due = record.date("due") { detail += " (due " + SemanticDates.display(due, timezone: workspace.timezone) + ")"; addClaim(record, "due", to: &result) }
            addClaim(record, field, to: &result)
            let prefix = family == .thread ? "\(record.timestamp.map { SemanticDates.display($0, timezone: workspace.timezone) } ?? "Time unknown") · \(label)" : label
            lines.append("\(prefix): \(detail) [\(record.id)]")
            result.excerpts.append(.init(record: record, label: prefix, text: text))
        }
        if records.count > 50 { result.limitations.append("Showing the first 50 matching records; more records are available."); incomplete = true }
        if family == .thread { result.limitations.append("Messages are presented in timestamp order. Earlier proposals are historical; later messages may correct them.") }
        result.answer = lines.isEmpty ? "No matching records in the available scope." : lines.joined(separator: "\n\n")
        if incomplete { result.status = .notCompleted }
        return result
    }

    private func addClaim(_ record: SemanticRecord, _ field: String, to result: inout SemanticResult) {
        guard let value = record.fields[field], value != .null else { return }
        let claim = SourceClaim(record: record, path: "/" + field, value: value)
        if !result.claims.contains(where: { $0.id == claim.id }) { result.claims.append(claim) }
    }

    private struct IdentitySelection {
        var selected: [SemanticRecord]?
        var ambiguities: [String] = []
        var field = "contact"
    }
    private func selectIdentity(_ records: [SemanticRecord], plan: SemanticPlan, turns: [String]) -> IdentitySelection {
        let question = plan.question
        let groupMode = plan.family == .thread || ["group", "chat", "family", "conversation"].contains { SemanticText.normalized(question).contains($0) }
        if groupMode {
            let groups = Dictionary(grouping: records, by: { "\($0.source.rawValue)/\($0.string("account"))/\($0.threadID)" })
            var matched: [(String, [SemanticRecord])] = []
            for (_, group) in groups {
                let names = group.flatMap { [$0.string("conversation"), $0.string("thread"), $0.string("subject").replacingOccurrences(of: "Re: ", with: "", options: .caseInsensitive)] }.filter { !$0.isEmpty }
                if names.contains(where: { name in
                    let significant = SemanticText.words(name).filter { !["re","fwd"].contains($0) }
                    return !significant.isEmpty && significant.allSatisfy { word in SemanticText.words(question).contains { SemanticText.matches($0, word) } }
                }) { matched.append((names.first ?? group[0].threadID, group)) }
            }
            if matched.count == 1 { return .init(selected: matched[0].1, field: "thread") }
            if matched.count > 1 { return .init(ambiguities: matched.map { $0.0 + " (" + ($0.1.first?.string("account") ?? "") + ")" }, field: "thread") }
        }
        // Keep sender addresses in the identity key: two Alexes at different addresses remain distinct.
        // Contact records are not consulted implicitly outside the recorded source scope.
        let identities = Set(records.map(\.sender).filter { !$0.isEmpty })
        func candidateNames(_ sender: String) -> [String] {
            let display = sender.components(separatedBy: "<")[0].trimmingCharacters(in: .whitespacesAndNewlines)
            return display.contains("@") ? [display, display.components(separatedBy: "@")[0].replacingOccurrences(of: ".", with: " ")] : [display, sender]
        }
        func candidates(_ text: String) -> [String] {
            let query = SemanticText.words(text)
            return identities.filter { sender in candidateNames(sender).contains { name in
                SemanticText.words(name).contains { word in word.count >= 3 && query.contains { SemanticText.matches($0, word) } }
            } }.sorted()
        }
        var matched = candidates(question)
        if matched.isEmpty, ["he", "she", "them", "him", "her"].contains(where: SemanticText.words(question).contains) {
            for previous in turns.dropLast().reversed() { matched = candidates(SemanticText.visibleRequest(previous)); if !matched.isEmpty { break } }
        }
        let full = matched.filter { sender in candidateNames(sender).contains { SemanticText.containsEntity(question, $0) } }
        if full.count == 1 { matched = full }
        if matched.count > 1 { return .init(ambiguities: matched) }
        guard let name = matched.first else { return .init() }
        var selected = records.filter { $0.sender == name && $0.fields["is_from_me"]?.bool != true && $0.string("direction").lowercased() != "outgoing" }
        if let about = question.range(of: "about ", options: .caseInsensitive) {
            let topic = SemanticText.words(String(question[about.upperBound...])).filter { !["today", "yesterday", "tomorrow", "please", "the", "in", "email", "emails", "mail", "messages", "texts"].contains($0) }
            if !topic.isEmpty { selected = selected.filter { record in topic.allSatisfy { SemanticText.words(record.body + " " + record.title).contains($0) } } }
        }
        return .init(selected: selected)
    }

    private func event(_ records: [SemanticRecord], plan: SemanticPlan, result initial: SemanticResult, workspace: SemanticWorkspace, incomplete: Bool) -> SemanticResult {
        var result = initial
        let stop = Set(["when","what","time","day","date","is","are","my","the","a","an","does","do","have","start","starts","for","at","on","in","calendar","event","scheduled","this","next","week","month","today","tomorrow","tommorow","please","appointment","monday","tuesday","wednesday","thursday","friday","saturday","sunday"])
        var query = SemanticText.words(plan.question.replacingOccurrences(of: #"\b\d{4}-\d{2}-\d{2}\b"#, with: "", options: .regularExpression).replacingOccurrences(of: "mid term", with: "midterm", options: .caseInsensitive)).filter { !stop.contains($0) }
        let assessment = Set(["test","exam","examination","assessment","midterm","quiz","final"])
        if plan.family == .fuzzyEvent, query.allSatisfy({ assessment.contains($0) || $0.allSatisfy(\.isNumber) }) {
            result.status = .clarify; result.answer = "Which subject or exam do you mean?"; result.clarificationFields = ["subject"]; return result
        }
        if query.isEmpty { result.status = .clarify; result.answer = "Which event do you mean?"; result.clarificationFields = ["event"]; return result }
        var incomplete = incomplete
        if records.contains(where: { $0.date("start") == nil }) {
            result.limitations.append("Some calendar records have unknown or invalid start times; absence of a match cannot be established."); incomplete = true
        }
        var candidates = records.filter { record in
            guard let start = record.date("start") else { return false }
            if let range = plan.range { return SemanticDates.overlaps(record, range) }
            return (record.date("end") ?? start) >= workspace.clock
        }
        let kind = query.first { assessment.contains($0) }
        query.removeAll { assessment.contains($0) }
        let scored = candidates.compactMap { record -> (SemanticRecord, Int)? in
            let title = SemanticText.words(record.title)
            if plan.family == .fuzzyEvent, let kind {
                let allowed: Set<String> = kind == "assessment" ? assessment : ["test","exam","examination"].contains(kind) ? ["exam","midterm","final","test"] : [kind]
                guard title.contains(where: allowed.contains) else { return nil }
            }
            let matches = query.filter { token in title.contains { SemanticText.matches(token, $0) } }
            guard matches.count == query.count else { return nil }
            return (record, matches.count + query.filter { title.contains($0) }.count)
        }
        if let top = scored.map(\.1).max() { candidates = scored.filter { $0.1 == top }.map(\.0) } else { candidates = [] }
        candidates.sort { ($0.date("start") ?? .distantFuture, $0.id) < ($1.date("start") ?? .distantFuture, $1.id) }
        // For a subject's repeated assessment, choose the next occurrence; unrelated tied titles clarify.
        if candidates.count > 1, plan.family != .fuzzyEvent,
           Set(candidates.map { SemanticText.normalized($0.title) }).count > 1 {
            result.status = .clarify; result.answer = "Which event: " + candidates.map(\.title).joined(separator: ", ") + "?"; result.clarificationFields = ["event"]; return result
        }
        guard let record = candidates.first, let start = record.date("start") else {
            result.answer = "No matching active event in the available calendar scope."; if incomplete { result.status = .notCompleted }; return result
        }
        addClaim(record, "start", to: &result); addClaim(record, "title", to: &result)
        result.answer = "\(record.title): \(SemanticDates.display(start, timezone: workspace.timezone)) [\(record.id)]"
        result.excerpts = [.init(record: record, label: record.title, text: result.answer)]
        if incomplete { result.status = .notCompleted }
        return result
    }

    private func groceries(_ records: [SemanticRecord], plan: SemanticPlan, result initial: SemanticResult, incomplete: Bool) -> SemanticResult {
        var result = initial
        let query = SemanticText.words(plan.question)
        let eligible = records.filter { record in
            let label = SemanticText.normalized(record.title + " " + record.string("list"))
            let words = label.split(separator: " ").map(String.init)
            let explicitList = words.filter { !["grocery","groceries","shopping","list","note","reminder"].contains($0) }.filter { query.contains($0) }
            let asksSpecificList = query.contains { token in records.contains { SemanticText.words($0.title + " " + $0.string("list")).contains(token) && !["grocery","groceries","shopping","list","note","reminder"].contains(token) } }
            let shopping = words.contains { ["grocery", "groceries", "shopping"].contains($0) } || ["grocery", "shopping"].contains(record.string("list_type").lowercased())
            return shopping && record.fields["items"]?.array != nil && (!asksSpecificList || !explicitList.isEmpty)
        }
        var unknown = false
        var quantities: [String: Set<String>] = [:]
        var display: [String: String] = [:]
        var order: [String] = []
        for record in eligible {
            guard let items = record.fields["items"]?.array else { continue }
            let open = items.filter { $0.object?["completed"]?.bool == false }
            for item in open {
                guard let fields = item.object, let name = fields["name"]?.string else { continue }
                let key = SemanticText.normalized(name)
                let quantity = fields["quantity"]?.string ?? ""
                if !quantity.isEmpty { quantities[key, default: []].insert(quantity) }
                let label = name + (quantity.isEmpty ? "" : " (\(quantity))")
                if display[key] == nil { order.append(key); display[key] = label }
                else if !quantity.isEmpty && display[key] == name { display[key] = label }
            }
            result.claims.append(.init(record: record, path: "/items", value: .array(open), predicate: "open_items"))
            result.excerpts.append(.init(record: record, label: record.title, text: record.body))
            if items.contains(where: { $0.object?["completed"]?.bool == nil }) { result.limitations.append("\(record.title): completion state unknown for some items; excluded."); unknown = true }
        }
        for key in quantities.keys.sorted() where quantities[key, default: []].count > 1 {
            display[key] = key + " (conflicting quantities: " + quantities[key, default: []].sorted().joined(separator: ", ") + ")"
            result.limitations.append("Conflicting quantities for \(key); not combined or guessed."); unknown = true
        }
        if eligible.isEmpty {
            result.status = .notCompleted; result.answer = "No structured shopping items in the selected sources."
            result.limitations.append("Plain text lists need explicit completion metadata; checked state was not guessed.")
        } else { result.answer = order.isEmpty ? "No explicitly open items in the available lists." : order.compactMap { display[$0] }.joined(separator: "\n") }
        if incomplete || unknown { result.status = .notCompleted }
        return result
    }

    private func weather(_ records: [SemanticRecord], plan: SemanticPlan, result initial: SemanticResult, workspace: SemanticWorkspace, incomplete: Bool) -> SemanticResult {
        var result = initial
        let candidates = records.filter { SemanticText.containsEntity(plan.question, $0.string("requested_city")) || SemanticText.containsEntity(plan.question, $0.string("resolved_city")) }
        guard candidates.count == 1, let record = candidates.first else {
            result.status = .clarify; result.answer = "Which city and region do you mean?"; result.clarificationFields = ["city","region"]; return result
        }
        guard SemanticText.normalized(record.string("requested_city")) == SemanticText.normalized(record.string("resolved_city")) else {
            result.status = .notCompleted; result.answer = ""; result.limitations.append("Weather provider resolved a different city; forecast excluded."); return result
        }
        if let requestedRegion = record.fields["requested_region"]?.string, let resolvedRegion = record.fields["resolved_region"]?.string,
           SemanticText.normalized(requestedRegion) != SemanticText.normalized(resolvedRegion) {
            result.status = .notCompleted; result.answer = ""; result.limitations.append("Weather provider resolved a different region; forecast excluded."); return result
        }
        if let range = plan.range, range.duration > 25 * 3600 {
            result.status = .clarify; result.answer = "Which day should I use for the forecast?"; result.clarificationFields = ["date"]; return result
        }
        let date = (plan.range?.start ?? workspace.clock)
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = workspace.timezone; formatter.dateFormat = "yyyy-MM-dd"
        let day = formatter.string(from: date)
        let forecast = record.fields["forecast"]?.array ?? []
        guard let index = forecast.firstIndex(where: { $0.object?["date"]?.string == day }), let fields = forecast[index].object else {
            result.status = .notCompleted; result.answer = ""; result.limitations.append("No forecast for the requested day."); return result
        }
        guard let city = fields["city"]?.string, SemanticText.normalized(city) == SemanticText.normalized(record.string("resolved_city")) else {
            result.status = .notCompleted; result.answer = ""; result.limitations.append("Forecast city is missing or differs from the resolved city; excluded."); return result
        }
        // Region comparison requires provider-supplied canonical metadata; no guessed state-name aliases.
        let canonicalRegion = record.fields["resolved_region"]?.string ?? record.fields["region_code"]?.string
        if let forecastRegion = fields["state"]?.string {
            guard let canonicalRegion, SemanticText.normalized(forecastRegion) == SemanticText.normalized(canonicalRegion) else {
                result.status = .notCompleted; result.answer = ""; result.limitations.append("Forecast region could not be verified against canonical location metadata; excluded."); return result
            }
        }
        result.claims = [.init(record: record, path: "/forecast/\(index)", value: forecast[index])]
        let high = fields["high_f"]?.number.map { String(format: "%.0f", $0) } ?? "unknown"
        let low = fields["low_f"]?.number.map { String(format: "%.0f", $0) } ?? "unknown"
        result.answer = "\(record.string("resolved_city")), \(record.string("region")) — \(day): high \(high)°F, low \(low)°F [\(record.id)]."
        result.excerpts = [.init(record: record, label: record.string("resolved_city"), text: result.answer)]
        if incomplete { result.status = .notCompleted }
        return result
    }

    private func preview(_ plan: SemanticPlan, workspace: SemanticWorkspace) -> SemanticResult {
        let fields = plan.family == .create ? ["kind", "title", "date", "timezone"] : plan.family == .meeting ? ["contact", "start", "duration"] : ["recipient", "channel", "content", "send_time"]
        return SemanticResult(family: plan.family, status: .clarify, answer: "Use the Action preview form to enter exact details. No action has been performed.",
                              limitations: ["Natural-language action extraction and native execution are not connected. The form creates a local preview only."],
                              clarificationFields: fields)
    }
}
