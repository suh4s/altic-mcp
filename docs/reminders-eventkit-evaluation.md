# Reminders backend: AppleScript vs EventKit

Evaluation of replacing the AppleScript Reminders backend (`reminders-manager.applescript`)
with a compiled Swift EventKit helper (`reminders-manager.swift`). Measured 2026-09-29.

## Verdict

Adopt EventKit. Reads went from **112 s** (timed out at the 60 s default) to **~85 ms**, about
**1,300x faster**, with identical IDs and content. Writes are ~100-130 ms. One capability is lost
(the `flagged` bit, which EventKit does not expose) and it now fails loudly instead of silently.

## Problem

`list_reminders` / `search_reminders` timed out through the MCP server on a store with only
23 open reminders in a single iCloud list. macOS permissions were ruled out: `list_lists` and
calendar calls succeeded and direct `osascript` could read Reminders.

Root cause: `collectReminders` set a lazy `whose` reference, then did ~6 separate Apple Event
round-trips per reminder (`name`, `id`, `body`, `priority`, `flagged`, `due date`), and each
round-trip re-evaluated the filter. Reminders answers every Apple Event slowly, so cost scaled as
O(reminders x properties).

## Method

- Machine: macOS 26.7.1, Apple Swift 6.4, iCloud-backed Reminders, 1 list, 23 open / 0 completed.
- Timing: wall clock via `time.perf_counter()` around a `subprocess.run`, n=5 per operation,
  median/min/max. Baseline is a single run (it is 2 minutes long).
- Baseline: the unmodified script from `HEAD` (`git show HEAD:tools/scripts/reminders-manager.applescript`),
  run with a 400 s timeout so it could finish.
- Parity: original output vs Swift output compared per reminder by `id`, field by field.
- Write operations were run against 5 throwaway reminders (`altic-eval-N`), then deleted.
  Leftover after the run: 0. Total reminders before/after: 23 / 23.

## Results

### Read path

| Approach | Time | Notes |
|---|---|---|
| Original AppleScript (HEAD) | **112 s** | Correct, but far over the 60 s `osascript_timeout_seconds` default |
| AppleScript, per-property bulk fetch (intermediate patch) | 29-31 s | One fetch per property; every fetch costs 4-6 s regardless of property |
| AppleScript, bulk fetch with `whose completed is false` | 37-47 s | Filter is re-evaluated per property; slower than unfiltered |
| AppleScript, single `properties of reminders` fetch | ~60 s | Heavy records; no better |
| **Swift EventKit, `list` open** | **86 ms** (85-89) | |
| Swift EventKit, `list` incl. completed | 81 ms (79-86) | |
| Swift EventKit, `search SBI` | 82 ms (81-87) | |
| Swift EventKit, `list_lists` | 84 ms (77-87) | |
| Through MCP, 3 calls, fresh server process | ~0.6-0.7 s total | Dominated by `uv` + Python startup |

Speedup for `list` open: 112,000 ms / 86 ms is about 1,300x (about 360x versus the intermediate patch).

### Write path (Swift, n=5)

| Operation | Median | Range |
|---|---|---|
| reschedule | 122 ms | 119-145 |
| update | 109 ms | 98-182 |
| complete | 128 ms | 108-131 |
| delete | 110 ms | 89-128 |
| `set_reminder` (still AppleScript) | 262 ms | 257-537 |

`set_reminder` was left on AppleScript: it creates a single item without scanning the list, so it
was never slow.

### One-time costs

- Cold compile (`swiftc -O`): **1.1 s**, once per source change, cached in `~/.cache/altic-mcp/`.
- macOS Reminders permission: no new prompt was shown for the helper in this environment.

## Parity (original vs Swift, `list` open)

| Check | Result |
|---|---|
| Count | 23 = 23 |
| Set of `id`s | identical |
| `name`, `completed`, `priority`, `list` | identical |
| `flagged` | 0 true in both (no flagged items in this store, so **not a real test**) |
| `body` | 22 differ: original emitted the literal string `"missing value"`, Swift emits `""` |
| `due` | 22 differ: same `"missing value"` bug. 1 dated item: `"Saturday, August 15, 2026 at 12:00:00 AM"` -> `"2026-08-15"` |

Every difference is either a fix (the `"missing value"` leak) or an intentional format change.
Completed-item check: AppleScript `count of (reminders whose completed is true)` = 0 and EventKit's
dedicated completed predicate = 0, so `include_completed` returning the same 23 is correct.
(An earlier `count of reminders` returned 155, which did not reproduce; treated as transient.)

## Behavior changes

| Area | Before | After |
|---|---|---|
| `flagged` | read/write via AppleScript | always `false`; `update_reminder(flagged=...)` returns an error (EventKit has no flag API) |
| `due` format | locale string | `YYYY-MM-DD HH:MM`, or `YYYY-MM-DD` for all-day |
| Empty `body` / `due` | `"missing value"` | `""` |
| Result order | Reminders internal order | sorted by due (undated first), then title |
| Runtime requirement | `osascript` | `swiftc` on first run / after source edits (the repo's other Swift tools already need the toolchain) |

## Verification

- `uv run pytest`: 105 passed (reminders tests updated for the new command shape).
- End-to-end through the MCP server: list, search, create, reschedule, update, complete, delete on a
  throwaway reminder, then confirmed it was gone.

## Limitations and risks

- Single machine, single small store (23 items). EventKit scales better, but larger stores were
  not measured. The AppleScript path is known to degrade with size.
- The 5-run samples are small; the `set_reminder` max of 537 ms is one outlier.
- `flagged` cannot be supported. If flagging matters, use priority, or keep an AppleScript path
  for that single write.
- `show` opens `x-apple-reminderkit://REMCDReminder/<id>`; it was not exercised in the live test.
- The compiled binary is cached outside the repo; a stale cache is handled by the mtime check, but
  a failed compile surfaces as a generic error string.
- Name-based lookups (`identifier` = title) fail with `match_count != 1` on duplicates, as before.

## Follow-up: Calendar on EventKit

Same root cause, same fix (`calendar-manager.swift`). Measured before/after through the MCP server:

| Operation | AppleScript | EventKit |
|---|---|---|
| `list_calendar_events_for_day` (all calendars) | 127 s | 118 ms |
| Panchanga (large subscribed calendar) `list` | timed out at 60 s | 125 ms |
| `check_calendar_availability` | timed out at 60 s | 113 ms |
| `list` 2-week range, all calendars | not measured | 137 ms |
| `search` 2 years, all calendars | not measured | 386 ms |
| `list_calendars` | 735 ms | ~0.1 s (first cold launch ~4 s) |

Notes and the simple Notes tools were already fast (0.4-2 s) and were left alone.

Verified live on a scratch calendar: create, availability conflict, update, dry-run delete, real delete,
create_recurring (3 occurrences expanded), series delete; 0 leftovers.

Behavior changes: recurring events are expanded into occurrences (AppleScript listed only stored
starts); events gain `all_day` and `recurring`; availability ignores all-day events; update keeps the
event length when only the start changes; update/delete on a recurring event apply to this and future
occurrences; `list_calendar_events_for_day` returns the structured `list` result instead of text;
`create_calendar_event` gained optional location/notes and returns the created event.

## Follow-ups

- Notes stays on AppleScript; revisit only if it shows scaling problems on a large notes library.
