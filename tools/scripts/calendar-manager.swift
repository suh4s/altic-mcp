import EventKit
import Foundation

// EventKit backend for calendar (same actions and JSON shapes as calendar-manager.applescript).
// AppleScript `whose` date filters scan every event of every calendar (minutes on large
// subscribed calendars); EventKit queries an index and expands recurring events.

let store = EKEventStore()
let args = Array(CommandLine.arguments.dropFirst())
let cal = Calendar.current

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
        store.requestFullAccessToEvents(completion: done)
    } else {
        store.requestAccess(to: .event, completion: done)
    }
    sem.wait()
    if !granted {
        fail("Calendar access denied (\(failure?.localizedDescription ?? "grant it in System Settings > Privacy & Security > Calendars"))")
    }
}

let dayFmt = DateFormatter()
dayFmt.dateFormat = "yyyy-MM-dd"
let timeFmt = DateFormatter()
timeFmt.dateFormat = "yyyy-MM-dd HH:mm"

func parseDate(_ text: String) -> Date {
    guard let d = dayFmt.date(from: text) else { fail("Date must be in format 'YYYY-MM-DD'") }
    return d
}

func parseDateTime(_ text: String) -> Date {
    guard let d = timeFmt.date(from: text) else { fail("DateTime must be in format 'YYYY-MM-DD HH:MM'") }
    return d
}

func endOfDay(_ d: Date) -> Date {
    return cal.date(byAdding: DateComponents(day: 1, second: -1), to: cal.startOfDay(for: d))!
}

func targetCalendars(_ name: String) -> [EKCalendar] {
    let all = store.calendars(for: .event)
    if name.isEmpty { return all }
    let match = all.filter { $0.title == name }
    if match.isEmpty { fail("Calendar not found: \(name)") }
    return match
}

func fetch(_ start: Date, _ end: Date, _ calendars: [EKCalendar]) -> [EKEvent] {
    if calendars.isEmpty { return [] }
    return store.events(matching: store.predicateForEvents(withStart: start, end: end, calendars: calendars))
        .sorted { $0.startDate < $1.startDate }
}

func eventId(_ e: EKEvent) -> String {
    return e.calendarItemExternalIdentifier ?? e.eventIdentifier ?? ""
}

func json(_ e: EKEvent) -> [String: Any] {
    let f = e.isAllDay ? dayFmt : timeFmt
    return [
        "id": eventId(e),
        "title": e.title ?? "",
        "calendar": e.calendar?.title ?? "",
        "start": f.string(from: e.startDate),
        "end": f.string(from: e.endDate),
        "location": e.location ?? "",
        "notes": e.notes ?? "",
        "all_day": e.isAllDay,
        "recurring": e.hasRecurrenceRules
    ]
}

let yearSeconds = 365.0 * 86400

func range(_ startText: String, _ endText: String) -> (Date, Date) {
    let start = startText.isEmpty ? Date().addingTimeInterval(-yearSeconds) : parseDate(startText)
    let end = endText.isEmpty ? Date().addingTimeInterval(yearSeconds) : endOfDay(parseDate(endText))
    return (start, end)
}

// One occurrence per series (recurring events repeat the same id across occurrences).
func findEvents(_ identifier: String, _ startText: String, _ endText: String, _ calName: String) -> [EKEvent] {
    let (start, end) = range(startText, endText)
    var seen = Set<String>()
    var out: [EKEvent] = []
    for e in fetch(start, end, targetCalendars(calName)) {
        if eventId(e) == identifier || e.eventIdentifier == identifier || e.title == identifier {
            if seen.insert(eventId(e) + "|" + (e.calendar?.title ?? "")).inserted { out.append(e) }
        }
    }
    return out
}

func matchOne(_ key: String, _ identifier: String, _ startText: String, _ endText: String, _ calName: String, extra: [String: Any] = [:]) -> EKEvent {
    let m = findEvents(identifier, startText, endText, calName)
    if m.count != 1 { emit([key: false, "match_count": m.count].merging(extra) { $1 }) }
    return m[0]
}

// Recurring events apply to this and future occurrences (the whole series when matched from its start).
func span(_ e: EKEvent) -> EKSpan { return e.hasRecurrenceRules ? .futureEvents : .thisEvent }

func save(_ e: EKEvent) {
    do { try store.save(e, span: span(e), commit: true) } catch { fail("Unable to save event: \(error.localizedDescription)") }
}

func newEvent(_ title: String, _ start: Date, _ minutes: Int, _ calName: String, _ location: String, _ notes: String) -> EKEvent {
    if minutes <= 0 { fail("Duration must be greater than 0 minutes") }
    let target: EKCalendar
    if calName.isEmpty {
        guard let d = store.defaultCalendarForNewEvents else { fail("No default calendar") }
        target = d
    } else {
        target = targetCalendars(calName)[0]
    }
    let e = EKEvent(eventStore: store)
    e.calendar = target
    e.title = title
    e.startDate = start
    e.endDate = start.addingTimeInterval(Double(minutes) * 60)
    if !location.isEmpty { e.location = location }
    if !notes.isEmpty { e.notes = notes }
    return e
}

guard let action = args.first else { fail("action is required") }
requestAccess()

switch action {
case "list_calendars":
    emit(["calendars": store.calendars(for: .event).map { $0.title }])

case "list":
    // args: start_date end_date calendar
    let start = parseDate(arg(1)), end = endOfDay(parseDate(arg(2)))
    let events = fetch(start, end, targetCalendars(arg(3))).map(json)
    emit(["events": events, "count": events.count])

case "search":
    // args: query start_date end_date calendar
    let query = arg(1)
    let (start, end) = range(arg(2), arg(3))
    let events = fetch(start, end, targetCalendars(arg(4))).filter {
        [$0.title, $0.location, $0.notes].compactMap { $0 }.joined(separator: " ")
            .localizedCaseInsensitiveContains(query)
    }.map(json)
    emit(["query": query, "events": events, "count": events.count])

case "create":
    // args: title start_datetime duration calendar location notes
    let e = newEvent(arg(1), parseDateTime(arg(2)), Int(arg(3)) ?? 0, arg(4), arg(5), arg(6))
    save(e)
    emit(["created": true, "event": json(e)])

case "update":
    // args: identifier title start_datetime duration calendar location notes
    let e = matchOne("updated", arg(1), "", "", arg(5))
    let originalLength = e.endDate.timeIntervalSince(e.startDate)
    if !arg(2).isEmpty { e.title = arg(2) }
    if !arg(3).isEmpty {
        e.startDate = parseDateTime(arg(3))
        e.endDate = e.startDate.addingTimeInterval(originalLength)  // keep length unless duration given
    }
    if let minutes = Int(arg(4)) { e.endDate = e.startDate.addingTimeInterval(Double(minutes) * 60) }
    if !arg(6).isEmpty { e.location = arg(6) }
    if !arg(7).isEmpty { e.notes = arg(7) }
    save(e)
    emit(["updated": true, "event": json(e)])

case "delete":
    // args: identifier start_date end_date calendar dry_run
    let dry = arg(5) == "true"
    let e = matchOne("deleted", arg(1), arg(2), arg(3), arg(4), extra: ["dry_run": dry])
    let data = json(e)
    if !dry {
        do { try store.remove(e, span: span(e), commit: true) } catch { fail("Unable to delete event: \(error.localizedDescription)") }
    }
    emit(["deleted": !dry, "dry_run": dry, "event": data])

case "availability":
    // args: start_datetime duration calendar. All-day events (birthdays, holidays) don't block.
    let start = parseDateTime(arg(1))
    guard let minutes = Int(arg(2)), minutes > 0 else { fail("Duration must be greater than 0 minutes") }
    let end = start.addingTimeInterval(Double(minutes) * 60)
    let conflicts = fetch(start, end, targetCalendars(arg(3)))
        .filter { !$0.isAllDay && $0.startDate < end && $0.endDate > start }
        .map(json)
    emit(["available": conflicts.isEmpty, "conflicts": conflicts, "count": conflicts.count])

case "create_recurring":
    // args: title start_datetime duration frequency interval count until_date calendar location notes
    let freqs: [String: (EKRecurrenceFrequency, String)] = [
        "daily": (.daily, "DAILY"), "weekly": (.weekly, "WEEKLY"),
        "monthly": (.monthly, "MONTHLY"), "yearly": (.yearly, "YEARLY")
    ]
    guard let (freq, freqName) = freqs[arg(4)] else { fail("frequency must be one of: daily, weekly, monthly, yearly") }
    let interval = Int(arg(5)) ?? 1
    var end: EKRecurrenceEnd?
    var rule = "FREQ=\(freqName);INTERVAL=\(interval)"
    if let count = Int(arg(6)) {
        end = EKRecurrenceEnd(occurrenceCount: count)
        rule += ";COUNT=\(count)"
    } else if !arg(7).isEmpty {
        end = EKRecurrenceEnd(end: endOfDay(parseDate(arg(7))))
        rule += ";UNTIL=\(arg(7))"
    }
    let e = newEvent(arg(1), parseDateTime(arg(2)), Int(arg(3)) ?? 0, arg(8), arg(9), arg(10))
    e.addRecurrenceRule(EKRecurrenceRule(recurrenceWith: freq, interval: interval, end: end))
    save(e)
    emit(["created": true, "recurrence": rule, "event": json(e)])

default:
    fail("unknown action: \(action)")
}
