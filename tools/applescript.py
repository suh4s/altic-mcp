"""Consolidated AppleScript runner for osascript-based manager scripts.

Replaces the five duplicated ``_run_manager`` helpers in calendar.py,
contacts.py, notes.py, reminders.py, and messages.py with a single
implementation that reads its default timeout from the runtime config.
"""

import json
import subprocess
from pathlib import Path

from . import config, result
from .constants import SCRIPTS_PREFIX


BIN_CACHE = Path.home() / ".cache" / "altic-mcp"


def _swift_binary(source: Path) -> Path:
    """Compile a Swift helper once and reuse it; rebuild when the source is newer."""
    binary = BIN_CACHE / source.stem
    if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
        BIN_CACHE.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["swiftc", "-O", str(source), "-o", str(binary)],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
    return binary


def run_manager(
    script_name: str,
    namespace: str,
    action: str,
    *args: str,
    timeout: int | None = None,
    permission_required: str | None = None,
) -> str:
    """Run an AppleScript manager script and return a structured result string.

    Args:
        script_name: Filename of the ``.applescript`` under ``tools/scripts/``.
        namespace: Tool namespace for the action label (e.g. ``"calendar"``).
        action: Action name passed as the first argument to the script.
        *args: Additional positional string arguments for the script.
        timeout: Optional timeout in seconds; defaults to the
            ``osascript_timeout_seconds`` config value.
        permission_required: Optional permission label included in error
            responses to guide the user toward granting access.

    Returns:
        JSON string produced by :func:`tools.result.ok` or
        :func:`tools.result.error`.
    """
    script_path = SCRIPTS_PREFIX / script_name
    tool_action = f"{namespace}.{action}"
    if timeout is None:
        timeout = config.get("osascript_timeout_seconds")

    try:
        if script_path.suffix == ".swift":
            command = [str(_swift_binary(script_path)), action, *args]
        else:
            command = ["osascript", str(script_path), action, *args]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if completed.returncode != 0:
            error_msg = completed.stderr.strip() or "Unknown error"
            return result.error(
                tool_action,
                error_msg,
                permission_required=permission_required,
            )

        stdout = completed.stdout.strip()
        data = {} if not stdout else json.loads(stdout)
        return result.ok(tool_action, data)
    except subprocess.TimeoutExpired:
        return result.error(tool_action, "Operation timed out", code="timeout")
    except Exception as exc:
        return result.error(tool_action, str(exc))


def run_script(
    script_name: str,
    *args: str,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    """Run an AppleScript and return the raw ``CompletedProcess``.

    Use this for simple scripts that don't follow the manager JSON protocol.
    """
    script_path = SCRIPTS_PREFIX / script_name
    return subprocess.run(
        ["osascript", str(script_path), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
