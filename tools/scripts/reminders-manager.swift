import EventKit
import Foundation

// EventKit backend for reminders (same actions and JSON shapes as reminders-manager.applescript).
// AppleScript costs ~5s per property fetch; EventKit answers in milliseconds.

let store = EKEventStore()
let args = Array(CommandLine.arguments.dropFirst())

func emit(_ object: [String: Any]) -> Never {
    let data = try! JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
    exit(0)
}

func fail(_ message: String) -> Never {
    fputs(message + "\n", stderr)
    exit(1)
}

func arg(_ i: Int) -> String { i < args.count ? args[i] : "" }

func requestAccess() {
    let sem = DispatchSemaphore(value: 0)
    var granted = false
    var failure: Error?
    let done: (Bool, Error?) -> Void = { ok, err in granted = ok; failure = err; sem.signal() }
    if #available(macOS 14.0, *) {
        store.requestFullAccessToReminders(completion: done)
    } else {
        store.requestAccess(to: .reminder, completion: done)
    }
    sem.wait()
    if !granted {
        fail("Reminders access denied (\(failure?.localizedDescription ?? "grant it in System Settings > Privacy & Security > Reminders"))")
    }
}

func fetchAll(in calendars: [EKCalendar]) -> [EKReminder] {
    let sem = DispatchSemaphore(value: 0)
    var out: [EKReminder] = []
    store.fetchReminders(matching: store.predicateForReminders(in: calendars)) { out = $0 ?? []; sem.signal() }
    sem.wait()
    return out
}

func targetCalendars(_ listName: String) -> [EKCalendar] {
    let all = store.calendars(for: .reminder)
    if listName.isEmpty { return all }
    let match = all.filter { $0.title == listName }
    if match.isEmpty { fail("Reminders list not found: \(listName)") }
    return match
}

let idPrefix = "x-apple-reminder://"

func dueString(_ r: EKReminder) -> String {
    guard let c = r.dueDateComponents, let y = c.year, let m = c.month, let d = c.day else { return "" }
    let date = String(format: "%04d-%02d-%02d", y, m, d)
    if let h = c.hour { return date + String(format: " %02d:%02d", h, c.minute ?? 0) }
    return date
}

func json(_ r: EKReminder) -> [String: Any] {
    return [
        "id": idPrefix + r.calendarItemIdentifier,
        "name": r.title ?? "",
        "list": r.calendar?.title ?? "",
        "completed": r.isCompleted,
        "due": dueString(r),
        "body": r.notes ?? "",
        "priority": r.priority,
        "flagged": false  // ponytail: EventKit does not expose the Reminders flag; use priority instead
    ]
}

func parseDateTime(_ text: String) -> DateComponents {
    let parts = text.split(separator: " ")
    guard parts.count == 2 else { fail("Date/time format must be 'YYYY-MM-DD HH:MM'") }
    let d = parts[0].split(separator: "-").compactMap { Int($0) }
    let t = parts[1].split(separator: ":").compactMap { Int($0) }
    guard d.count == 3, t.count == 2 else { fail("Date/time format must be 'YYYY-MM-DD HH:MM'") }
    var c = DateComponents()
    c.calendar = Calendar.current
    c.timeZone = TimeZone.current
    c.year = d[0]; c.month = d[1]; c.day = d[2]; c.hour = t[0]; c.minute = t[1]
    return c
}

func findMatches(_ identifier: String, _ listName: String) -> [EKReminder] {
    let all = fetchAll(in: targetCalendars(listName))
    let bare = identifier.hasPrefix(idPrefix) ? String(identifier.dropFirst(idPrefix.count)) : identifier
    let byId = all.filter { $0.calendarItemIdentifier == bare }
    return byId.isEmpty ? all.filter { $0.title == identifier } : byId
}

func save(_ r: EKReminder) {
    do { try store.save(r, commit: true) } catch { fail("Unable to save reminder: \(error.localizedDescription)") }
}

func matchOne(_ key: String, _ identifier: String, _ listName: String, extra: [String: Any] = [:]) -> EKReminder {
    let m = findMatches(identifier, listName)
    if m.count != 1 { emit([key: false, "match_count": m.count].merging(extra) { $1 }) }
    return m[0]
}

guard let action = args.first else { fail("action is required") }
requestAccess()

switch action {
case "list_lists":
    emit(["lists": store.calendars(for: .reminder).map { $0.title }])

case "list", "search":
    let isSearch = action == "search"
    let query = isSearch ? arg(1) : ""
    let listName = arg(isSearch ? 2 : 1)
    let includeCompleted = arg(isSearch ? 3 : 2) == "true"
    let items = fetchAll(in: targetCalendars(listName))
        .filter { includeCompleted || !$0.isCompleted }
        .filter { query.isEmpty || ($0.title ?? "").localizedCaseInsensitiveContains(query) }
        .sorted { (dueString($0), $0.title ?? "") < (dueString($1), $1.title ?? "") }
        .map(json)
    var out: [String: Any] = ["reminders": items, "count": items.count]
    if isSearch { out["query"] = query }
    emit(out)

case "complete":
    let r = matchOne("completed", arg(1), arg(2))
    r.isCompleted = true
    save(r)
    emit(["completed": true, "reminder": json(r)])

case "delete":
    let dry = arg(3) == "true"
    let r = matchOne("deleted", arg(1), arg(2), extra: ["dry_run": dry])
    let data = json(r)
    if !dry { do { try store.remove(r, commit: true) } catch { fail("Unable to delete reminder: \(error.localizedDescription)") } }
    emit(["deleted": !dry, "dry_run": dry, "reminder": data])

case "reschedule":
    let due = parseDateTime(arg(2))
    let r = matchOne("rescheduled", arg(1), arg(3))
    r.dueDateComponents = due
    save(r)
    emit(["rescheduled": true, "reminder": json(r)])

case "update":
    // args: id list name body datetime completed priority flagged
    let r = matchOne("updated", arg(1), arg(2))
    if !arg(3).isEmpty { r.title = arg(3) }
    if !arg(4).isEmpty { r.notes = arg(4) }
    if !arg(5).isEmpty { r.dueDateComponents = parseDateTime(arg(5)) }
    if arg(6) == "true" { r.isCompleted = true }
    if arg(6) == "false" { r.isCompleted = false }
    if let p = Int(arg(7)) { r.priority = p }
    if !arg(8).isEmpty { fail("flagged is not supported by the EventKit backend") }
    save(r)
    emit(["updated": true, "reminder": json(r)])

case "show":
    let r = matchOne("shown", arg(1), arg(2))
    if let url = URL(string: "x-apple-reminderkit://REMCDReminder/\(r.calendarItemIdentifier)") {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        p.arguments = [url.absoluteString]
        try? p.run()
        p.waitUntilExit()
    }
    emit(["shown": true, "reminder": json(r)])

default:
    fail("unknown action: \(action)")
}
