import Foundation

public enum SemanticDates {
    public static func parse(_ text: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: text) { return date }
        formatter.formatOptions.insert(.withFractionalSeconds)
        return formatter.date(from: text)
    }
    public static func iso(_ date: Date, timezone: TimeZone) -> String {
        let formatter = ISO8601DateFormatter(); formatter.timeZone = timezone
        return formatter.string(from: date)
    }
    public static func calendar(_ timezone: TimeZone) -> Calendar {
        var calendar = Calendar(identifier: .gregorian); calendar.timeZone = timezone
        calendar.firstWeekday = 2; calendar.minimumDaysInFirstWeek = 4
        return calendar
    }
    public static func range(question: String, clock: Date, timezone: TimeZone, defaultToday: Bool = false) -> DateInterval? {
        let text = SemanticText.normalized(question)
        let calendar = calendar(timezone)
        // Explicit dates take precedence over relative words and never silently become today.
        if let match = question.range(of: #"\b\d{4}-\d{2}-\d{2}\b"#, options: .regularExpression) {
            let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = timezone; formatter.dateFormat = "yyyy-MM-dd"; formatter.isLenient = false
            guard let date = formatter.date(from: String(question[match])) else { return nil }
            return calendar.dateInterval(of: .day, for: date)
        }
        let weekdays = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
        if let index = weekdays.firstIndex(where: SemanticText.words(text).contains) {
            let current = calendar.component(.weekday, from: clock) - 1
            var offset = (index - current + 7) % 7
            if text.contains("next " + weekdays[index]) && offset == 0 { offset = 7 }
            if let date = calendar.date(byAdding: .day, value: offset, to: clock) { return calendar.dateInterval(of: .day, for: date) }
        }
        if text.contains("next week"), let week = calendar.dateInterval(of: .weekOfYear, for: clock), let start = calendar.date(byAdding: .weekOfYear, value: 1, to: week.start), let end = calendar.date(byAdding: .weekOfYear, value: 1, to: start) { return DateInterval(start: start, end: end) }
        if text.contains("this week") || text.contains("for the week") { return calendar.dateInterval(of: .weekOfYear, for: clock) }
        if text.contains("next month"), let month = calendar.date(byAdding: .month, value: 1, to: clock) { return calendar.dateInterval(of: .month, for: month) }
        if text.contains("this month") || text.contains("for the month") { return calendar.dateInterval(of: .month, for: clock) }
        let tomorrow = ["tomorrow", "tmrow", "tmrw", "tommorow", "tomorow"].contains { SemanticText.words(text).contains($0) }
        if tomorrow, let date = calendar.date(byAdding: .day, value: 1, to: clock) { return calendar.dateInterval(of: .day, for: date) }
        if text.contains("yesterday"), let date = calendar.date(byAdding: .day, value: -1, to: clock) { return calendar.dateInterval(of: .day, for: date) }
        if defaultToday || text.contains("today") || text.contains("this morning") || text.contains("tonight") { return calendar.dateInterval(of: .day, for: clock) }
        return nil
    }
    public static func overlaps(_ record: SemanticRecord, _ range: DateInterval) -> Bool {
        guard let start = record.date("start") else { return false }
        if let end = record.date("end"), end > start { return start < range.end && end > range.start }
        return start >= range.start && start < range.end
    }
    public static func display(_ date: Date, timezone: TimeZone) -> String {
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = timezone
        formatter.dateFormat = "EEE, MMM d, yyyy 'at' h:mm a zzz"
        return formatter.string(from: date)
    }
}

public enum SemanticText {
    public static func normalized(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .replacingOccurrences(of: "[’']", with: "", options: .regularExpression)
            .replacingOccurrences(of: "[^a-z0-9@.+]+", with: " ", options: .regularExpression)
            .split(separator: " ").joined(separator: " ")
    }
    public static func words(_ text: String) -> [String] { normalized(text).split(separator: " ").map(String.init) }
    public static func distance(_ left: String, _ right: String) -> Int {
        let a = Array(left), b = Array(right)
        var previous = Array(0...b.count)
        for (i, char) in a.enumerated() {
            var current = [i + 1]
            for (j, other) in b.enumerated() { current.append(min(current[j] + 1, previous[j+1] + 1, previous[j] + (char == other ? 0 : 1))) }
            previous = current
        }
        return previous[b.count]
    }
    public static func matches(_ query: String, _ candidate: String) -> Bool {
        if query == candidate { return true }
        guard min(query.count, candidate.count) >= 4, max(query.count, candidate.count) <= 64 else { return false }
        return distance(query, candidate) <= (min(query.count, candidate.count) >= 7 ? 2 : 1)
    }
    public static func containsEntity(_ question: String, _ name: String) -> Bool {
        let query = words(question), entity = words(name)
        return !entity.isEmpty && entity.allSatisfy { token in query.contains { matches($0, token) } }
    }
    public static func visibleRequest(_ text: String) -> String {
        // Never interpret an embedded quoted command as the requested operation.
        text.replacingOccurrences(of: #""[^"\n]*"|“[^”\n]*”|`[^`\n]*`"#, with: " ", options: .regularExpression)
    }
}
