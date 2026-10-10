import Foundation

/// Production routing uses user turns and records only. Gold family is deliberately ignored.
public struct Workflow20SemanticAdapter: Sendable {
    public init() {}
    public func observe(_ input: Workflow20Input) throws -> Workflow20Observation {
        let workspace = try SemanticWorkspace(scenario: input.scenario)
        let result = SemanticEngine().respond(turns: input.turns.filter { $0.role == "user" }.map(\.text), in: workspace)
        let claims = try JSONDecoder().decode(JSONValue.self, from: JSONEncoder().encode(result.claims))
        return Workflow20Observation(case_id: input.caseID, status: result.status.rawValue, facts: [], reads: result.reads.map(\.rawValue),
            tool_calls: [], approval: .init(requested: false, granted: false, approved_effects: []), effects: [], answer: result.answer,
            clarification_fields: result.clarificationFields, limitations: result.limitations,
            metrics: ["inference_executed": .bool(false), "adapter_mode": .string("bounded_source_semantics"),
                      "routed_family": result.family.map { .string($0.rawValue) } ?? .null, "source_claims": claims,
                      "fact_alias_bridge": .string("unavailable: canonical claims are not arbitrary oracle fact IDs")])
    }
}
