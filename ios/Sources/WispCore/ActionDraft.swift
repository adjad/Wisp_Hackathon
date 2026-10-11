import Foundation

public enum PreviewKind: String, CaseIterable, Sendable { case reminder, event, message }
public enum PreviewError: Error, LocalizedError {
    case missing(String), invalidInterval, tooLarge
    public var errorDescription: String? {
        switch self {
        case .missing(let field): "Enter \(field)."
        case .invalidInterval: "The event end must be after its start."
        case .tooLarge: "Preview text is limited to 4,000 bytes per field."
        }
    }
}
/// Explicit user input only. Building/confirming this value never creates a native effect.
public struct ActionDraft: Sendable {
    public var kind: PreviewKind
    public var title: String
    public var recipient: String
    public var channel: String
    public var content: String
    public var start: Date
    public var end: Date
    public var timezone: TimeZone
    public init(kind: PreviewKind, title: String = "", recipient: String = "", channel: String = "email", content: String = "",
                start: Date, end: Date, timezone: TimeZone) {
        self.kind = kind; self.title = title; self.recipient = recipient; self.channel = channel; self.content = content
        self.start = start; self.end = end; self.timezone = timezone
    }
    public func preview() throws -> ActionPreview {
        func required(_ value: String, _ name: String) throws -> String {
            guard !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw PreviewError.missing(name) }
            guard value.utf8.count <= 4000 else { throw PreviewError.tooLarge }
            return value // Preserve the exact reviewed payload; no normalization after approval.
        }
        var params: [String: JSONValue] = ["timezone": .string(timezone.identifier), "start": .string(SemanticDates.iso(start, timezone: timezone))]
        switch kind {
        case .reminder: params["title"] = .string(try required(title, "a reminder title"))
        case .event:
            guard end > start else { throw PreviewError.invalidInterval }
            params["title"] = .string(try required(title, "an event title"))
            params["end"] = .string(SemanticDates.iso(end, timezone: timezone))
        case .message:
            params["recipient"] = .string(try required(recipient, "the exact recipient address or number"))
            params["channel"] = .string(try required(channel, "a channel"))
            params["content"] = .string(try required(content, "message content"))
        }
        return ActionPreview(type: kind.rawValue, params: params)
    }
}
