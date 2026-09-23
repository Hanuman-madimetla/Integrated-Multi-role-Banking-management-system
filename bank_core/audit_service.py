from __future__ import annotations

import sqlite3
from typing import Optional

from .db import read_only
from .permissions import EmployeeSession, require_role


class AuditService:
    """Single place where every audit record is written."""

    def log(
        self,
        conn: sqlite3.Connection,
        action: str,
        details: str = "",
        employee_id: Optional[int] = None,
        actor: Optional[str] = None,
    ) -> None:
        # Always called with the caller's connection, so the audit row commits
        # or rolls back together with the operation it describes.
        conn.execute(
            """INSERT INTO audit_logs(employee_id, actor, action, details)
               VALUES (?, ?, ?, ?)""",
            (employee_id, actor, action, details),
        )

    def recent(self, session: EmployeeSession, limit: int = 50) -> list[sqlite3.Row]:
        with read_only() as conn:
            require_role(conn, session, "manager")
            return conn.execute(
                """
                SELECT l.log_id, l.timestamp, l.action, l.details,
                       COALESCE(e.username, l.actor, 'system') AS who
                FROM audit_logs l
                LEFT JOIN employees e ON e.employee_id = l.employee_id
                ORDER BY l.log_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()


audit_service = AuditService()
