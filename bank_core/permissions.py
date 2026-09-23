from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class EmployeeSession:
    """What every dashboard receives after login."""
    employee_id: int
    username: str
    role: str


def require_role(conn: sqlite3.Connection, session: EmployeeSession, *roles: str) -> None:
    """
    Server-side role check used by every employee-only service call.

    It re-reads the employee from the database, so a suspended employee or a
    tampered session object can never perform an action.
    """
    row = conn.execute(
        "SELECT role, status FROM employees WHERE employee_id = ?",
        (session.employee_id,),
    ).fetchone()

    if (
        row is None
        or row["status"] != "active"
        or row["role"] != session.role
        or row["role"] not in roles
    ):
        raise PermissionError(
            f"Action requires role: {', '.join(roles)}"
        )
