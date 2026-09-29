import json
import subprocess
from pathlib import Path

from tools import calendar


def read_json(value: str):
    payload = json.loads(value)
    assert payload["ok"] is True, payload
    return payload


def test_list_calendars_invokes_manager(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout='{"calendars":["Home","Work"]}',
            stderr="",
        )

    monkeypatch.setattr(calendar.applescript.subprocess, "run", fake_run)

    payload = read_json(calendar.list_calendars())

    assert payload["action"] == "calendar.list_calendars"
    assert payload["data"] == {"calendars": ["Home", "Work"]}
    assert Path(seen["args"][0]).name == "calendar-manager"
    assert seen["args"][1:] == ["list_calendars"]


def test_list_calendar_events_validates_date_range(monkeypatch):
    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(calendar.applescript.subprocess, "run", fail_run)

    payload = json.loads(calendar.list_calendar_events("2026-07-10", "2026-07-01"))

    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation_error"
    assert "start_date must be on or before end_date" in payload["error"]["message"]


def test_search_calendar_events_serializes_args(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout='{"events":[]}',
            stderr="",
        )

    monkeypatch.setattr(calendar.applescript.subprocess, "run", fake_run)

    payload = read_json(
        calendar.search_calendar_events("demo", "2026-07-01", "2026-07-31", "Work")
    )

    assert payload["action"] == "calendar.search"
    assert seen["args"][1:] == ["search", "demo", "2026-07-01", "2026-07-31", "Work"]


def test_delete_calendar_event_defaults_to_dry_run(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout='{"deleted":false}',
            stderr="",
        )

    monkeypatch.setattr(calendar.applescript.subprocess, "run", fake_run)

    payload = read_json(calendar.delete_calendar_event("Weekly sync"))

    assert payload["action"] == "calendar.delete"
    assert seen["args"][1:] == ["delete", "Weekly sync", "", "", "", "true"]


def test_check_calendar_availability_validates_duration(monkeypatch):
    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(calendar.applescript.subprocess, "run", fail_run)

    payload = json.loads(calendar.check_calendar_availability("2026-07-01 09:00", 0))

    assert payload["ok"] is False
    assert payload["error"]["message"] == "Duration must be greater than 0 minutes"


def test_create_recurring_event_serializes_recurrence(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout='{"created":true,"event":{"id":"EVT-1","title":"Standup"}}',
            stderr="",
        )

    monkeypatch.setattr(calendar.applescript.subprocess, "run", fake_run)

    payload = read_json(
        calendar.create_recurring_event(
            title="Standup",
            start_datetime="2026-07-06 09:00",
            duration_minutes=30,
            frequency="weekly",
            interval=1,
            count=10,
            until_date="",
            calendar_name="Work",
            location="Zoom",
            notes="Team sync",
        )
    )

    assert payload["action"] == "calendar.create_recurring"
    assert payload["data"]["created"] is True
    assert seen["args"][1:] == [
        "create_recurring",
        "Standup",
        "2026-07-06 09:00",
        "30",
        "weekly",
        "1",
        "10",
        "",
        "Work",
        "Zoom",
        "Team sync",
    ]


def test_create_recurring_event_validates_frequency(monkeypatch):
    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(calendar.applescript.subprocess, "run", fail_run)

    payload = json.loads(
        calendar.create_recurring_event(
            title="Standup",
            start_datetime="2026-07-06 09:00",
            duration_minutes=30,
            frequency="sometimes",
        )
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation_error"


def test_list_events_for_day_uses_single_day_list(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout='{"events":[],"count":0}', stderr=""
        )

    monkeypatch.setattr(calendar.applescript.subprocess, "run", fake_run)

    payload = json.loads(calendar.list_calendar_events_for_day("2026-09-29"))

    assert payload["ok"] is True
    assert seen["args"][1:] == ["list", "2026-09-29", "2026-09-29", ""]
    assert json.loads(calendar.list_calendar_events_for_day("tomorrow"))["ok"] is False


def test_create_calendar_event_validates_and_serializes(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout='{"created":true,"event":{}}', stderr=""
        )

    monkeypatch.setattr(calendar.applescript.subprocess, "run", fake_run)

    assert json.loads(calendar.create_calendar_event("x", "bad", 30))["ok"] is False
    assert json.loads(calendar.create_calendar_event("x", "2026-10-02 09:00", 0))["ok"] is False
    assert json.loads(calendar.create_calendar_event(" ", "2026-10-02 09:00", 30))["ok"] is False
    assert "args" not in seen

    payload = json.loads(calendar.create_calendar_event("Sync", "2026-10-02 09:00", 30, "Work"))
    assert payload["ok"] is True
    assert seen["args"][1:] == ["create", "Sync", "2026-10-02 09:00", "30", "Work", "", ""]
