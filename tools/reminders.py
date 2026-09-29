from datetime import datetime as _datetime

from . import applescript, result


def validate_time_format(time: str) -> tuple[bool, str]:
    """
    Validate that time is 'YYYY-MM-DD HH:MM' (timed) or 'YYYY-MM-DD' (all-day).
    Returns (is_valid, error_message).
    """
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            _datetime.strptime(time, fmt)
            return True, ""
        except ValueError:
            pass
    return (
        False,
        "Time must be in format 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD' (e.g., '2025-10-27 14:30')",
    )


def _bool_arg(value: bool) -> str:
    return "true" if value else "false"


def _run_manager(action: str, *args: str, timeout: int | None = None) -> str:
    return applescript.run_manager(
        "reminders-manager.swift",
        "reminders",
        action,
        *args,
        timeout=timeout,
        permission_required="Reminders",
    )


def _validate_identifier(action: str, identifier: str) -> str | None:
    if not identifier or not identifier.strip():
        return result.error(
            action,
            "identifier cannot be empty",
            code="validation_error",
        )
    return None


def list_reminder_lists() -> str:
    return _run_manager("list_lists")


def list_reminders(list_name: str = "", include_completed: bool = False) -> str:
    return _run_manager("list", list_name, _bool_arg(include_completed))


def search_reminders(
    query: str,
    list_name: str = "",
    include_completed: bool = False,
) -> str:
    if not query or not query.strip():
        return result.error(
            "reminders.search",
            "query cannot be empty",
            code="validation_error",
        )
    return _run_manager("search", query, list_name, _bool_arg(include_completed))


def complete_reminder(identifier: str, list_name: str = "") -> str:
    validation = _validate_identifier("reminders.complete", identifier)
    if validation:
        return validation
    return _run_manager("complete", identifier, list_name)


def delete_reminder(
    identifier: str,
    list_name: str = "",
    dry_run: bool = True,
) -> str:
    validation = _validate_identifier("reminders.delete", identifier)
    if validation:
        return validation
    return _run_manager("delete", identifier, list_name, _bool_arg(dry_run))


def reschedule_reminder(identifier: str, datetime: str, list_name: str = "") -> str:
    validation = _validate_identifier("reminders.reschedule", identifier)
    if validation:
        return validation

    is_valid, error_msg = validate_time_format(datetime)
    if not is_valid:
        return result.error(
            "reminders.reschedule",
            error_msg,
            code="validation_error",
        )
    return _run_manager("reschedule", identifier, datetime, list_name)


def update_reminder(
    identifier: str,
    list_name: str = "",
    name: str = "",
    body: str = "",
    datetime: str = "",
    completed: bool | None = None,
    priority: int | None = None,
    flagged: bool | None = None,
) -> str:
    validation = _validate_identifier("reminders.update", identifier)
    if validation:
        return validation

    if datetime:
        is_valid, error_msg = validate_time_format(datetime)
        if not is_valid:
            return result.error("reminders.update", error_msg, code="validation_error")

    if priority is not None and not 0 <= priority <= 9:
        return result.error(
            "reminders.update",
            "priority must be between 0 and 9",
            code="validation_error",
        )

    completed_arg = "" if completed is None else _bool_arg(completed)
    priority_arg = "" if priority is None else str(priority)
    flagged_arg = "" if flagged is None else _bool_arg(flagged)

    return _run_manager(
        "update",
        identifier,
        list_name,
        name,
        body,
        datetime,
        completed_arg,
        priority_arg,
        flagged_arg,
    )


def show_reminder(identifier: str, list_name: str = "") -> str:
    validation = _validate_identifier("reminders.show", identifier)
    if validation:
        return validation
    return _run_manager("show", identifier, list_name)


def set_reminder(name: str, time: str, list_name: str = "") -> str:
    return create_reminder(name, time, list_name)


def create_reminder(
    name: str,
    datetime: str = "",
    list_name: str = "",
    body: str = "",
    priority: int | None = None,
) -> str:
    if not name or not name.strip():
        return result.error("reminders.create", "name cannot be empty", code="validation_error")
    if datetime:
        is_valid, error_msg = validate_time_format(datetime)
        if not is_valid:
            return result.error("reminders.create", error_msg, code="validation_error")
    if priority is not None and not 0 <= priority <= 9:
        return result.error(
            "reminders.create", "priority must be between 0 and 9", code="validation_error"
        )
    return _run_manager(
        "create", name, datetime, list_name, body, "" if priority is None else str(priority)
    )


def create_reminder_list(name: str) -> str:
    if not name or not name.strip():
        return result.error("reminders.create_list", "name cannot be empty", code="validation_error")
    return _run_manager("create_list", name)


def move_reminder(identifier: str, to_list: str, list_name: str = "") -> str:
    validation = _validate_identifier("reminders.move", identifier)
    if validation:
        return validation
    if not to_list or not to_list.strip():
        return result.error("reminders.move", "to_list cannot be empty", code="validation_error")
    return _run_manager("move", identifier, list_name, to_list)
