import SwiftUI
import UniformTypeIdentifiers

struct HomeView: View {
    @State private var workspace = SemanticDemo.workspace()
    @State private var question = "What is on my calendar today?"
    @State private var turns: [String] = []
    @State private var importSource = SourceKind.messages
    @State private var structuredImport = false
    @State private var showImporter = false
    @State private var importError: String?
    @State private var result: SemanticResult?
    @State private var kind = PreviewKind.reminder
    @State private var title = ""
    @State private var recipient = ""
    @State private var channel = "email"
    @State private var content = ""
    @State private var start = Date()
    @State private var end = Date().addingTimeInterval(3600)
    @State private var preview: ActionPreview?
    @State private var approval: PreviewApproval?
    @State private var previewError: String?

    var body: some View {
        TabView {
            NavigationStack {
                List {
                    Section {
                        Label(workspace.origin == .synthetic ? "Synthetic demo" : "Selected import", systemImage: "lock.shield").font(.headline)
                        Text("Ask about the supplied records. No accounts or AI model are connected.")
                        Text("Source clock: \(SemanticDates.display(workspace.clock, timezone: workspace.timezone))").font(.caption).foregroundStyle(.secondary)
                    }
                    Section("Ask Wisp") {
                        TextField("Ask about a contact, calendar or list", text: $question, axis: .vertical)
                            .lineLimit(2...5).accessibilityIdentifier("question")
                        Button("Ask") { ask() }.disabled(question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            .accessibilityIdentifier("ask-wisp")
                        Menu("Try a demo question") {
                            ForEach(["What is on my calendar today?", "What did Mira say in messages?", "Summarize Garden volunteers messages thread", "What groceries should I buy from notes?", "When is my astronomy test?", "Unread email", "Daily briefing"], id: \.self) { example in
                                Button(example) { question = example; ask() }
                            }
                        }
                        if !turns.isEmpty { Button("Start a new question", role: .cancel) { turns = []; result = nil } }
                    }
                    if let result {
                        Section(result.family?.title ?? "Wisp") {
                            Text(statusTitle(result.status)).font(.headline)
                            if !result.answer.isEmpty { Text(result.answer).textSelection(.enabled) }
                            if !result.clarificationFields.isEmpty { Text("Details needed: " + result.clarificationFields.joined(separator: ", ")) }
                            ForEach(result.limitations, id: \.self) { Text($0).font(.caption).foregroundStyle(.secondary) }
                        }
                        if !result.excerpts.isEmpty {
                            Section("Source evidence") {
                                ForEach(result.excerpts) { excerpt in
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text(excerpt.label).font(.headline)
                                        if !excerpt.text.isEmpty { Text(excerpt.text).textSelection(.enabled) }
                                        Text("\(excerpt.record.source.rawValue) · \(excerpt.record.id)").font(.caption).foregroundStyle(.secondary)
                                    }.padding(.vertical, 4)
                                }
                            }
                        }
                    }
                    Section("Bring selected records") {
                        Toggle("Structured JSON", isOn: $structuredImport)
                        if !structuredImport {
                            Picker("Text source", selection: $importSource) {
                                ForEach([SourceKind.messages, .email, .notes, .memory], id: \.self) { Text($0.rawValue).tag($0) }
                            }
                        }
                        PasteButton(payloadType: String.self) { values in if let text = values.first { importData(Data(text.utf8)) } }
                        Button("Import a file") { showImporter = true }
                        Text("Replaces this in-memory workspace. Limit: 64 KiB. Plain text has no assumed sender, dates or unread state. Structured records include explicit metadata and a source clock.")
                            .font(.caption).foregroundStyle(.secondary)
                        Button("Reset to synthetic demo") { workspace = SemanticDemo.workspace(); turns = []; result = nil }
                    }
                }.navigationTitle("Wisp")
                .fileImporter(isPresented: $showImporter, allowedContentTypes: structuredImport ? [.json] : [.plainText]) { selection in
                    do {
                        let url = try selection.get(); let granted = url.startAccessingSecurityScopedResource()
                        defer { if granted { url.stopAccessingSecurityScopedResource() } }
                        let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
                        importData(try handle.read(upToCount: TextImport.maximumBytes + 1) ?? Data())
                    } catch { importError = error.localizedDescription }
                }
                .alert("Import could not finish", isPresented: Binding(get: { importError != nil }, set: { if !$0 { importError = nil } })) {
                    Button("OK", role: .cancel) { importError = nil }
                } message: { Text(importError ?? "") }
            }.tabItem { Label("Workspace", systemImage: "text.bubble") }
            NavigationStack {
                Form {
                    Section {
                        Text("Build an exact local preview. Confirmation records your review in memory. Nothing is sent, scheduled or saved to another app.")
                    }
                    Section("Details") {
                        Picker("Kind", selection: $kind) { ForEach(PreviewKind.allCases, id: \.self) { Text($0.rawValue.capitalized).tag($0) } }
                        if kind == .message {
                            TextField("Exact recipient address or number", text: $recipient).textInputAutocapitalization(.never).autocorrectionDisabled()
                            Picker("Channel", selection: $channel) { Text("Email").tag("email"); Text("Message").tag("message") }
                            TextField("Content", text: $content, axis: .vertical)
                        } else { TextField("Title", text: $title) }
                        DatePicker(kind == .message ? "Requested send time" : "Start / due", selection: $start)
                        if kind == .event { DatePicker("End", selection: $end) }
                        Text("Timezone: \(TimeZone.current.identifier)").font(.caption)
                        Button("Build preview") { makePreview() }
                        if let previewError { Text(previewError).foregroundStyle(.red) }
                    }
                    if let preview {
                        Section("Review exact preview") {
                            Text(preview.type.capitalized).font(.headline)
                            ForEach(preview.params.keys.sorted(), id: \.self) { key in
                                LabeledContent(key, value: preview.params[key]?.string ?? "")
                            }
                            if let approval, preview.matches(approval) {
                                Label("Preview reviewed — no action performed", systemImage: "checkmark.circle")
                            } else {
                                Button("Confirm this preview only") { approval = PreviewApproval(preview: preview) }
                            }
                        }
                    }
                }.navigationTitle("Action preview")
                .onChange(of: draftFingerprint) { _, _ in preview = nil; approval = nil; previewError = nil }
            }.tabItem { Label("Preview", systemImage: "doc.text.magnifyingglass") }
            NavigationStack {
                List {
                    Section("Platform access") {
                        ForEach(PlatformCapability.baseline, id: \.name) { capability in
                            VStack(alignment: .leading, spacing: 6) { Text(capability.name).font(.headline); Text(capability.detail).font(.subheadline).foregroundStyle(.secondary) }.padding(.vertical, 4)
                        }
                    }
                    Section("Local AI") {
                        Text("The optional on-device model adapter is disabled. No model has been activated or measured.")
                        Text("Queries use bounded deterministic matching over supplied records. This prototype does not yet support all twenty workflows.").font(.caption).foregroundStyle(.secondary)
                    }
                }.navigationTitle("Capabilities")
            }.tabItem { Label("Capabilities", systemImage: "checklist") }
        }.tint(.indigo)
    }
    private var draftFingerprint: [String] { [kind.rawValue, title, recipient, channel, content, String(start.timeIntervalSince1970), String(end.timeIntervalSince1970)] }
    private func ask() {
        turns.append(question); turns = Array(turns.suffix(20))
        result = SemanticEngine().respond(turns: turns, in: workspace)
    }
    private func makePreview() {
        do { preview = try ActionDraft(kind: kind, title: title, recipient: recipient, channel: channel, content: content, start: start, end: end, timezone: .current).preview(); approval = nil; previewError = nil }
        catch { preview = nil; approval = nil; previewError = error.localizedDescription }
    }
    private func importData(_ data: Data) {
        do {
            workspace = structuredImport ? try StructuredImport.workspace(data) : try SemanticWorkspace.converted(TextImport.workspace(data: data, source: importSource, clock: Date()))
            turns = []; result = nil
        } catch { importError = error.localizedDescription }
    }
    private func statusTitle(_ status: ResultStatus) -> String {
        switch status {
        case .answered: "Result from available records"
        case .clarify: "More details needed"
        case .prepared: "Preview only"
        case .notCompleted: "Partial or incomplete result"
        case .unsupported: "Not connected"
        }
    }
}
