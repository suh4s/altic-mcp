import json
import subprocess
from pathlib import Path

from tools import applescript


def test_run_manager_success(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout='{"events":[]}', stderr=""
        )

    monkeypatch.setattr(applescript.subprocess, "run", fake_run)

    result = json.loads(applescript.run_manager("calendar-manager.applescript", "calendar", "list"))

    assert result["ok"] is True
    assert result["action"] == "calendar.list"
    assert result["data"] == {"events": []}
    assert seen["args"][0] == "osascript"
    assert Path(seen["args"][1]).name == "calendar-manager.applescript"
    assert seen["args"][2:] == ["list"]
    assert seen["kwargs"]["timeout"] == 60  # default from config


def test_run_manager_error_includes_permission(monkeypatch):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args, returncode=1, stdout="", stderr="not authorized"
        )

    monkeypatch.setattr(applescript.subprocess, "run", fake_run)

    result = json.loads(
        applescript.run_manager(
            "contacts-manager.applescript",
            "contacts",
            "get",
            "Ada",
            permission_required="Contacts",
        )
    )

    assert result["ok"] is False
    assert result["error"]["message"] == "not authorized"
    assert result["error"]["permission_required"] == "Contacts"


def test_run_manager_timeout(monkeypatch):
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=5)

    monkeypatch.setattr(applescript.subprocess, "run", fake_run)

    result = json.loads(applescript.run_manager("notes-manager.applescript", "notes", "list"))

    assert result["ok"] is False
    assert result["error"]["code"] == "timeout"


def test_run_manager_custom_timeout(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(applescript.subprocess, "run", fake_run)

    applescript.run_manager("x.applescript", "x", "act", timeout=120)
    assert seen["kwargs"]["timeout"] == 120


def test_run_manager_compiles_and_runs_swift_helper(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout='{"lists":[]}', stderr=""
        )

    monkeypatch.setattr(applescript, "BIN_CACHE", tmp_path)
    monkeypatch.setattr(applescript.subprocess, "run", fake_run)

    first = json.loads(applescript.run_manager("reminders-manager.swift", "reminders", "list_lists"))
    assert first["ok"] is True
    assert calls[0][0] == "swiftc"  # no cached binary yet -> compile
    assert Path(calls[1][0]) == tmp_path / "reminders-manager"
    assert calls[1][1:] == ["list_lists"]

    (tmp_path / "reminders-manager").touch()  # cached and newer than source -> no recompile
    calls.clear()
    applescript.run_manager("reminders-manager.swift", "reminders", "list_lists")
    assert [Path(c[0]).name for c in calls] == ["reminders-manager"]
