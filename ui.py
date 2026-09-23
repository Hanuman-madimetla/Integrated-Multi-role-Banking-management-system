from __future__ import annotations

import sqlite3


def ask_int(prompt: str) -> int:
    raw = input(prompt).strip()
    try:
        return int(raw)
    except ValueError:
        raise ValueError("Please enter a whole number")


def header(title: str, session=None) -> None:
    print(f"\n=== {title} ===")
    if session is not None:
        print(f"Employee #{session.employee_id} | {session.username} | {session.role}")


# Errors every menu action is allowed to raise without crashing the app.
HANDLED_ERRORS = (ValueError, PermissionError, sqlite3.Error)
