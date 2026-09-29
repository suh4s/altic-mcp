from datetime import datetime
from typing import Tuple

from . import applescript, result

VALID_RECURRENCE_FREQUENCIES = {"daily", "weekly", "monthly", "yearly"}


def validate_datetime_format(datetime_str: str) -> Tuple[bool, str]:
    try:
        datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        return True, ""
    except ValueError:
        return (
            False,
            "DateTime must be in format 'YYYY-MM-DD HH:MM' (e.g., '2025-10-30 14:30')",
        )


def validate_date_format(date_str: str) -> Tuple[bool, str]:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True, ""
    except ValueError:
        return (
            False,
            "Date must be in format 'YYYY-MM-DD' (e.g., '2025-10-30')",
        )


def create_calendar_event(
    title: str,
    start_datetime: str,
    duration_minutes: int,
    calendar_name: str = "",
    location: str = "",
    notes: str = "",
) -> str:
    if not title or not title.strip():
        return result.error("calendar.create", "title cannot be empty", code="validation_error")
    is_valid, error_msg = validate_datetime_format(start_datetime)
    if not is_valid:
        return result.error("calendar.create", error_msg, code="validation_error")
    if duration_minutes <= 0:
        return result.error(
            "calendar.create",
            "Duration must be greater than 0 minutes",
            code="validation_error",
        )
    return _run_manager(
        "create", title.strip(), start_datetime, str(duration_minutes), calendar_name, location, notes
    )


def list_calendar_events_for_day(date: str) -> str:
    """List all calendar events for a specific day ('YYYY-MM-DD') across all calendars."""
    is_valid, error_msg = validate_date_format(date)
    if not is_valid:
        return result.error("calendar.list", error_msg, code="validation_error")
    return _run_manager("list", date, date, "")


def _bool_arg(value: bool) -> str:
    return "true" if value else "false"


def _parse_date(date: str) -> datetime:
    return datetime.strptime(date, "%Y-%m-%d")


def _run_manager(action: str, *args: str, timeout: int | None = None) -> str:
    return applescript.run_manager(
        "calendar-manager.swift",
        "calendar",
        action,
        *args,
        timeout=timeout,
        permission_required="Calendars",
    )


def _validate_date_range(action: str, start_date: str, end_date: str) -> str | None:
    start_ok, start_error = validate_date_format(start_date)
    if not start_ok:
        return result.error(action, start_error, code="validation_error")

    end_ok, end_error = validate_date_format(end_date)
    if not end_ok:
        return result.error(action, end_error, code="validation_error")

    if _parse_date(start_date) > _parse_date(end_date):
        return result.error(
            action,
            "start_date must be on or before end_date",
            code="validation_error",
        )
    return None


def _validate_identifier(action: str, identifier: str) -> str | None:
    if not identifier or not identifier.strip():
        return result.error(
            action,
            "identifier cannot be empty",
            code="validation_error",
        )
    return None


def list_calendars() -> str:
    return _run_manager("list_calendars")


def list_calendar_events(
    start_date: str,
    end_date: str,
    calendar_name: str = "",
) -> str:
    validation = _validate_date_range("calendar.list", start_date, end_date)
    if validation:
        return validation
    return _run_manager("list", start_date, end_date, calendar_name)


def search_calendar_events(
    query: str,
    start_date: str = "",
    end_date: str = "",
    calendar_name: str = "",
) -> str:
    if not query or not query.strip():
        return result.error(
            "calendar.search",
            "query cannot be empty",
            code="validation_error",
        )
    return _run_manager("search", query, start_date, end_date, calendar_name)


def update_calendar_event(
    identifier: str,
    title: str = "",
    start_datetime: str = "",
    duration_minutes: int | None = None,
    calendar_name: str = "",
    location: str = "",
    notes: str = "",
) -> str:
    validation = _validate_identifier("calendar.update", identifier)
    if validation:
        return validation
    if start_datetime:
        is_valid, error_msg = validate_datetime_format(start_datetime)
        if not is_valid:
            return result.error("calendar.update", error_msg, code="validation_error")
    if duration_minutes is not None and duration_minutes <= 0:
        return result.error(
            "calendar.update",
            "Duration must be greater than 0 minutes",
            code="validation_error",
        )
    return _run_manager(
        "update",
        identifier,
        title,
        start_datetime,
        "" if duration_minutes is None else str(duration_minutes),
        calendar_name,
        location,
        notes,
    )


def delete_calendar_event(
    identifier: str,
    start_date: str = "",
    end_date: str = "",
    calendar_name: str = "",
    dry_run: bool = True,
) -> str:
    validation = _validate_identifier("calendar.delete", identifier)
    if validation:
        return validation
    return _run_manager(
        "delete",
        identifier,
        start_date,
        end_date,
        calendar_name,
        _bool_arg(dry_run),
    )


def check_calendar_availability(
    start_datetime: str,
    duration_minutes: int,
    calendar_name: str = "",
) -> str:
    is_valid, error_msg = validate_datetime_format(start_datetime)
    if not is_valid:
        return result.error("calendar.availability", error_msg, code="validation_error")
    if duration_minutes <= 0:
        return result.error(
            "calendar.availability",
            "Duration must be greater than 0 minutes",
            code="validation_error",
        )
    return _run_manager(
        "availability",
        start_datetime,
        str(duration_minutes),
        calendar_name,
    )


def create_recurring_event(
    title: str,
    start_datetime: str,
    duration_minutes: int,
    frequency: str,
    interval: int = 1,
    count: int | None = None,
    until_date: str = "",
    calendar_name: str = "",
    location: str = "",
    notes: str = "",
) -> str:
    if not title or not title.strip():
        return result.error(
            "calendar.create_recurring",
            "title cannot be empty",
            code="validation_error",
        )
    is_valid, error_msg = validate_datetime_format(start_datetime)
    if not is_valid:
        return result.error(
            "calendar.create_recurring",
            error_msg,
            code="validation_error",
        )
    if duration_minutes <= 0:
        return result.error(
            "calendar.create_recurring",
            "Duration must be greater than 0 minutes",
            code="validation_error",
        )
    normalized_frequency = frequency.strip().lower()
    if normalized_frequency not in VALID_RECURRENCE_FREQUENCIES:
        return result.error(
            "calendar.create_recurring",
            "frequency must be one of: daily, weekly, monthly, yearly",
            code="validation_error",
        )
    if interval <= 0:
        return result.error(
            "calendar.create_recurring",
            "interval must be greater than 0",
            code="validation_error",
        )
    if count is not None and count <= 0:
        return result.error(
            "calendar.create_recurring",
            "count must be greater than 0 when provided",
            code="validation_error",
        )
    if until_date:
        until_ok, until_error = validate_date_format(until_date)
        if not until_ok:
            return result.error(
                "calendar.create_recurring",
                until_error,
                code="validation_error",
            )
    if count is not None and until_date:
        return result.error(
            "calendar.create_recurring",
            "provide count or until_date, not both",
            code="validation_error",
        )

    return _run_manager(
        "create_recurring",
        title.strip(),
        start_datetime,
        str(duration_minutes),
        normalized_frequency,
        str(interval),
        "" if count is None else str(count),
        until_date,
        calendar_name,
        location,
        notes,
    )
