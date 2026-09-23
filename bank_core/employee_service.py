from __future__ import annotations

import sqlite3
from typing import Optional

from .audit_service import audit_service
from .db import read_only, transaction
from .permissions import EmployeeSession, require_role
from .security import hash_password, needs_rehash, verify_password

ROLES = ("cashier", "field_officer", "accountant", "manager")


class EmployeeService:
    def authenticate(self, username: str, password: str) -> Optional[EmployeeSession]:
        with transaction() as conn:
            emp = conn.execute(
                "SELECT * FROM employees WHERE username = ?", (username,)
            ).fetchone()

            if emp is None:
                audit_service.log(conn, "login_failed", f"Unknown username: {username}")
                return None

            if emp["status"] != "active":
                audit_service.log(conn, "login_failed", "Suspended account",
                                  employee_id=emp["employee_id"])
                return None

            if not verify_password(password, emp["password_hash"]):
                audit_service.log(conn, "login_failed", "Incorrect password",
                                  employee_id=emp["employee_id"])
                return None

            if needs_rehash(emp["password_hash"]):
                conn.execute(
                    "UPDATE employees SET password_hash = ? WHERE employee_id = ?",
                    (hash_password(password), emp["employee_id"]),
                )

            audit_service.log(conn, "login_success", f"Role: {emp['role']}",
                              employee_id=emp["employee_id"])
            return EmployeeSession(emp["employee_id"], emp["username"], emp["role"])

    def logout(self, session: EmployeeSession) -> None:
        with transaction() as conn:
            audit_service.log(conn, "logout", "", employee_id=session.employee_id)

    def count(self) -> int:
        with read_only() as conn:
            return conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]

    def bootstrap_first_manager(self, username: str, password: str) -> int:
        """Only works while the employees table is empty."""
        self._validate(username, password)
        with transaction() as conn:
            if conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] > 0:
                raise PermissionError("Employees already exist")
            cur = conn.execute(
                "INSERT INTO employees(username, password_hash, role) VALUES (?, ?, 'manager')",
                (username, hash_password(password)),
            )
            audit_service.log(conn, "employee_bootstrap", f"First manager {username}",
                              employee_id=cur.lastrowid)
            return int(cur.lastrowid)

    def create_employee(self, session: EmployeeSession, username: str,
                        password: str, role: str) -> int:
        if role not in ROLES:
            raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
        self._validate(username, password)
        with transaction() as conn:
            require_role(conn, session, "manager")
            cur = conn.execute(
                "INSERT INTO employees(username, password_hash, role) VALUES (?, ?, ?)",
                (username, hash_password(password), role),
            )
            audit_service.log(conn, "employee_created", f"{username} ({role})",
                              employee_id=session.employee_id)
            return int(cur.lastrowid)

    def set_status(self, session: EmployeeSession, employee_id: int, status: str) -> None:
        if status not in ("active", "suspended"):
            raise ValueError("Invalid status")
        if employee_id == session.employee_id:
            raise ValueError("You cannot change your own status")
        with transaction() as conn:
            require_role(conn, session, "manager")
            cur = conn.execute(
                "UPDATE employees SET status = ? WHERE employee_id = ?",
                (status, employee_id),
            )
            if cur.rowcount != 1:
                raise ValueError("Employee not found")
            audit_service.log(conn, f"employee_{status}", f"Employee {employee_id}",
                              employee_id=session.employee_id)

    def list_employees(self, session: EmployeeSession) -> list[sqlite3.Row]:
        with read_only() as conn:
            require_role(conn, session, "manager")
            return conn.execute(
                "SELECT employee_id, username, role, status FROM employees ORDER BY employee_id"
            ).fetchall()

    @staticmethod
    def _validate(username: str, password: str) -> None:
        if len(username.strip()) < 3:
            raise ValueError("Username must have at least 3 characters")
        if len(password) < 8:
            raise ValueError("Employee password must have at least 8 characters")


employee_service = EmployeeService()
