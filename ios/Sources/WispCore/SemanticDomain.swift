import Foundation

public struct SemanticRecord: Sendable, Equatable, Identifiable {
    public let source: SourceKind
    public let fields: [String: JSONValue]
    public var id: String { fields["id"]?.string ?? "" }
    public init(source: SourceKind, fields: [String: JSONValue]) { self.source = source; self.fields = fields }
    public func string(_ key: String) -> String { fields[key]?.string ?? "" }
    public func date(_ key: String) -> Date? { SemanticDates.parse(string(key)) }
    public var title: String { ["title", "subject", "conversation", "name"].map(string).first(where: { !$0.isEmpty }) ?? source.rawValue }
    public var body: String { ["body", "text"].map(string).first(where: { !$0.isEmpty }) ?? "" }
    public var sender: String { string("sender") }
    public var timestamp: Date? { ["timestamp", "received", "sent", "modified", "start"].compactMap(date).first }
    public var threadID: String { ["thread_id", "conversation_id", "conversation", "thread"].map(string).first(where: { !$0.isEmpty }) ?? id }
    public var inactive: Bool { fields["completed"]?.bool == true || fields["cancelled"]?.bool == true || ["cancelled", "canceled", "deleted"].contains(string("status").lowercased()) }
}

public struct SemanticSource: Sendable {
    public let state: SourceState
    public let complete: Bool
    public let records: [SemanticRecord]
    public init(state: SourceState, complete: Bool, records: [SemanticRecord]) { self.state = state; self.complete = complete; self.records = records }
}

public struct SemanticWorkspace: Sendable {
    public let origin: DataOrigin
    public let clock: Date
    public let timezone: TimeZone
    public let sources: [SourceKind: SemanticSource]
    public init(origin: DataOrigin, clock: Date, timezone: TimeZone, sources: [SourceKind: SemanticSource]) {
        self.origin = origin; self.clock = clock; self.timezone = timezone; self.sources = sources
    }
    public init(scenario: Workflow20Corpus.Scenario) throws {
        guard let clock = SemanticDates.parse(scenario.clock), let timezone = TimeZone(identifier: scenario.timezone) else { throw ContractError.invalidScenario }
        var sources: [SourceKind: SemanticSource] = [:]
        for (name, source) in scenario.sources {
            guard let kind = SourceKind(rawValue: name) else { throw ContractError.invalidScenario }
            sources[kind] = .init(state: source.state, complete: source.complete, records: try source.records.map {
                guard let fields = $0.object, let id = fields["id"]?.string, !id.isEmpty else { throw ContractError.invalidScenario }
                return SemanticRecord(source: kind, fields: fields)
            })
        }
        self.init(origin: .synthetic, clock: clock, timezone: timezone, sources: sources)
    }
    public static func converted(_ workspace: Workspace) -> SemanticWorkspace {
        var sources: [SourceKind: SemanticSource] = [:]
        for (kind, snapshot) in workspace.sources {
            sources[kind] = .init(state: snapshot.state, complete: snapshot.complete, records: snapshot.records.map { record in
                var fields: [String: JSONValue] = ["id": .string(record.id), "body": .string(record.text)]
                if let sender = record.sender { fields["sender"] = .string(sender) }
                if let thread = record.thread { fields["thread"] = .string(thread) }
                if let start = record.start { fields["start"] = .string(SemanticDates.iso(start, timezone: workspace.timezone)) }
                if let end = record.end { fields["end"] = .string(SemanticDates.iso(end, timezone: workspace.timezone)) }
                if let unread = record.unread { fields["unread"] = .bool(unread) }
                return SemanticRecord(source: kind, fields: fields)
            })
        }
        return .init(origin: workspace.origin, clock: workspace.clock, timezone: workspace.timezone, sources: sources)
    }
}

/// Claims use production fields, never benchmark-specific fact aliases. Values remain unchanged.
public struct SourceClaim: Codable, Sendable, Equatable, Identifiable {
    public let source: String
    public let record_id: String
    public let path: String
    public let value: JSONValue
    public let context: String
    public let predicate: String
    public let source_ids: [String]
    public var id: String { "\(source)/\(record_id)/\(path)/\(context)" }
    public init(record: SemanticRecord, path: String, value: JSONValue, context: String = "record", predicate: String = "field") {
        self.source = record.source.rawValue; self.record_id = record.id; self.path = path; self.value = value; self.context = context
        self.predicate = predicate; self.source_ids = [record.id]
    }
}
public struct SemanticExcerpt: Sendable, Equatable, Identifiable {
    public let record: SemanticRecord
    public let label: String
    public let text: String
    public var id: String { record.source.rawValue + "/" + record.id }
}
public struct ActionPreview: Sendable, Equatable, Identifiable {
    public let id: UUID
    public let type: String
    public let params: [String: JSONValue]
    public let sourceIDs: [String]
    public init(type: String, params: [String: JSONValue], sourceIDs: [String] = []) {
        self.id = UUID(); self.type = type; self.params = params; self.sourceIDs = sourceIDs
    }
    public func matches(_ approval: PreviewApproval) -> Bool {
        approval.previewID == id && approval.type == type && approval.params == params && approval.sourceIDs == sourceIDs
    }
}
/// Confirmation is bound to an immutable preview, and cannot authorize native execution.
public struct PreviewApproval: Sendable {
    public let previewID: UUID
    public let type: String
    public let params: [String: JSONValue]
    public let sourceIDs: [String]
    public init(preview: ActionPreview) { previewID = preview.id; type = preview.type; params = preview.params; sourceIDs = preview.sourceIDs }
}
public struct SemanticResult: Sendable {
    public var family: WorkflowFamily?
    public var status: ResultStatus
    public var answer: String
    public var claims: [SourceClaim] = []
    public var excerpts: [SemanticExcerpt] = []
    public var reads: [SourceKind] = []
    public var limitations: [String] = []
    public var clarificationFields: [String] = []
    public var previews: [ActionPreview] = []
}

public enum StructuredImport {
    public static func workspace(_ data: Data) throws -> SemanticWorkspace {
        guard data.count <= TextImport.maximumBytes else { throw ImportError.tooLarge }
        let scenario = try JSONDecoder().decode(Workflow20Corpus.Scenario.self, from: data)
        let value = try SemanticWorkspace(scenario: scenario)
        let records = value.sources.values.flatMap(\.records)
        guard Set(records.map(\.id)).count == records.count else { throw ContractError.duplicateID }
        return .init(origin: .userImport, clock: value.clock, timezone: value.timezone, sources: value.sources)
    }
}
