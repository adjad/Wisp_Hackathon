import Foundation

#if WISP_REMOTE_FULL && WISP_FOUNDER_DEMO
#error("WISP_REMOTE_FULL builds choose the Aria demo at runtime; do not also compile WISP_FOUNDER_DEMO")
#endif
#if WISP_REMOTE_FULL && !WISP_REMOTE_ONLY_DEMO
#error("WISP_REMOTE_FULL requires WISP_REMOTE_ONLY_DEMO (pinned GX10 inference, bundled backend)")
#endif

/// The Intel v5 (`WISP_REMOTE_FULL`) runtime switch between real mode and the
/// Aria founder demo.
///
/// Real mode (default): the backend gets `WISP_REMOTE_FULL=1` — real data, the
/// full tool set under the normal approval policy, the scheduler, and behavior
/// learning from real activity. Aria demo mode: the backend gets
/// `WISP_FOUNDER_DEMO=1` instead — fictional Notes/Reminders/Contacts, the
/// read-only tool allowlist, synthetic behavior, and its own state directory.
/// The backend refuses to start with both, so exactly one is ever passed.
///
/// The choice persists in UserDefaults (the menu-bar toggle). Launching the app
/// with `WISP_FOUNDER_DEMO=1` forces demo mode regardless of the saved choice.
enum AriaDemoMode {
    static let defaultsKey = "wisp.ariaDemoMode"
    static let founderKey = "WISP_FOUNDER_DEMO"
    static let fullKey = "WISP_REMOTE_FULL"
    static let remoteOnlyKey = "WISP_REMOTE_ONLY"

    /// True when this binary offers the runtime switch at all.
    static var available: Bool {
#if WISP_REMOTE_FULL
        return true
#else
        return false
#endif
    }

    static func forcedByEnvironment(_ environment: [String: String] = ProcessInfo.processInfo.environment) -> Bool {
        environment[founderKey] == "1"
    }

    /// The effective mode for the next backend launch.
    static func isOn(defaults: UserDefaults = .standard,
                     environment: [String: String] = ProcessInfo.processInfo.environment) -> Bool {
#if WISP_REMOTE_FULL
        return forcedByEnvironment(environment) || defaults.bool(forKey: defaultsKey)
#elseif WISP_FOUNDER_DEMO
        return true
#else
        return false
#endif
    }

    /// Saves the toggle. Returns the new effective mode (an environment force
    /// still wins, so turning the toggle off cannot leave a forced demo).
    @discardableResult
    static func setSaved(_ on: Bool, defaults: UserDefaults = .standard,
                         environment: [String: String] = ProcessInfo.processInfo.environment) -> Bool {
        defaults.set(on, forKey: defaultsKey)
        return isOn(defaults: defaults, environment: environment)
    }

    /// Maps the mode onto the backend's launch environment for a v5 build:
    /// always `WISP_REMOTE_ONLY=1`, then exactly one of `WISP_REMOTE_FULL=1`
    /// (real) or `WISP_FOUNDER_DEMO=1` (demo). Any inherited value of either
    /// key is replaced, so the mapping alone decides the backend mode.
    static func applyBackendMode(demo: Bool, to environment: inout [String: String]) {
        environment[remoteOnlyKey] = "1"
        if demo {
            environment[founderKey] = "1"
            environment.removeValue(forKey: fullKey)
        } else {
            environment[fullKey] = "1"
            environment.removeValue(forKey: founderKey)
        }
    }
}
