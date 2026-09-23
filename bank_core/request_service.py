from __future__ import annotations

import sqlite3

from .audit_service import audit_service
from .db import read_only, transaction
from .money import format_paise
from .permissions import EmployeeSession, require_role


class RequestService:
    """Registration and deactivation pipelines (requests.db -> accounts.db)."""

    # ============================ registration ============================
    def list_pending_registrations(self, session: EmployeeSession) -> list[sqlite3.Row]:
        """Field officer queue."""
        with read_only() as conn:
            require_role(conn, session, "field_officer")
            return conn.execute(
                """SELECT request_id, customer_id, username, customer_name, submitted_at
                   FROM requests_db.registrations
                   WHERE status = 'pending' ORDER BY submitted_at"""
            ).fetchall()

    def list_verified_registrations(self, session: EmployeeSession) -> list[sqlite3.Row]:
        """Accountant queue."""
        with read_only() as conn:
            require_role(conn, session, "accountant")
            return conn.execute(
                """SELECT request_id, customer_id, username, customer_name, verified_at
                   FROM requests_db.registrations
                   WHERE status = 'verified' ORDER BY verified_at"""
            ).fetchall()

    def verify_registration(self, session: EmployeeSession, request_id: int) -> None:
        with transaction() as conn:
            require_role(conn, session, "field_officer")
            row = conn.execute(
                "SELECT customer_id FROM requests_db.registrations "
                "WHERE request_id = ? AND status = 'pending'", (request_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Pending registration not found")

            conn.execute(
                """UPDATE requests_db.registrations
                   SET status = 'verified', verified_by = ?, verified_at = CURRENT_TIMESTAMP
                   WHERE request_id = ? AND status = 'pending'""",
                (session.employee_id, request_id),
            )
            audit_service.log(conn, "registration_verified",
                              f"Customer {row['customer_id']}", employee_id=session.employee_id)

    def reject_registration(self, session: EmployeeSession, request_id: int, reason: str) -> None:
        """Field officer rejects 'pending'; accountant rejects 'verified'."""
        if not reason.strip():
            raise ValueError("A rejection reason is required")

        with transaction() as conn:
            require_role(conn, session, "field_officer", "accountant")
            stage = "pending" if session.role == "field_officer" else "verified"
            row = conn.execute(
                "SELECT customer_id FROM requests_db.registrations "
                "WHERE request_id = ? AND status = ?", (request_id, stage)
            ).fetchone()
            if row is None:
                raise ValueError(f"No {stage} registration with that ID")

            conn.execute(
                """UPDATE requests_db.registrations
                   SET status = 'rejected', rejected_by = ?, rejected_at = CURRENT_TIMESTAMP,
                       rejection_reason = ?
                   WHERE request_id = ?""",
                (session.employee_id, reason.strip(), request_id),
            )
            audit_service.log(conn, "registration_rejected",
                              f"Customer {row['customer_id']}; Reason: {reason.strip()}",
                              employee_id=session.employee_id)

    def approve_registration(self, session: EmployeeSession, request_id: int) -> int:
        """Accountant approval: creates the account atomically."""
        with transaction() as conn:
            require_role(conn, session, "accountant")
            req = conn.execute(
                "SELECT * FROM requests_db.registrations "
                "WHERE request_id = ? AND status = 'verified'", (request_id,)
            ).fetchone()
            if req is None:
                raise ValueError("Only a field-officer-verified request can be approved")

            if conn.execute(
                "SELECT 1 FROM accounts_db.accounts WHERE customer_id = ? OR username = ?",
                (req["customer_id"], req["username"]),
            ).fetchone():
                raise ValueError("Customer account already exists")

            account_id = int(conn.execute(
                """INSERT INTO accounts_db.accounts
                   (customer_id, username, customer_name, password_hash)
                   VALUES (?, ?, ?, ?)""",
                (req["customer_id"], req["username"], req["customer_name"], req["password_hash"]),
            ).lastrowid)

            conn.execute(
                """UPDATE requests_db.registrations
                   SET status = 'approved', approved_by = ?, approved_at = CURRENT_TIMESTAMP
                   WHERE request_id = ?""",
                (session.employee_id, request_id),
            )
            audit_service.log(conn, "registration_approved",
                              f"Request {request_id}; Account {account_id}",
                              employee_id=session.employee_id)
            return account_id

    # ============================ deactivation ============================
    def list_pending_deactivations(self, session: EmployeeSession) -> list[sqlite3.Row]:
        with read_only() as conn:
            require_role(conn, session, "accountant")
            return conn.execute(
                """SELECT d.request_id, d.account_id, d.reason, d.submitted_at,
                          a.customer_id, a.username, a.balance_paise
                   FROM requests_db.deactivations d
                   JOIN accounts_db.accounts a ON a.account_id = d.account_id
                   WHERE d.status = 'pending' ORDER BY d.submitted_at"""
            ).fetchall()

    def process_deactivation(self, session: EmployeeSession, request_id: int) -> tuple[bool, str]:
        """
        Accountant checks the balance:
            balance > 0  -> request is REJECTED automatically
            balance == 0 -> request APPROVED and account set to 'deactivated'
        Returns (approved, message). Both outcomes are committed.
        """
        with transaction() as conn:
            require_role(conn, session, "accountant")
            req = conn.execute(
                "SELECT account_id FROM requests_db.deactivations "
                "WHERE request_id = ? AND status = 'pending'", (request_id,)
            ).fetchone()
            if req is None:
                raise ValueError("Pending deactivation request not found")

            acc = conn.execute(
                "SELECT status, balance_paise FROM accounts_db.accounts WHERE account_id = ?",
                (req["account_id"],),
            ).fetchone()
            if acc is None or acc["status"] != "active":
                raise ValueError("Account is not active")

            if acc["balance_paise"] > 0:
                reason = f"Account still holds {format_paise(acc['balance_paise'])}"
                conn.execute(
                    """UPDATE requests_db.deactivations
                       SET status = 'rejected', processed_by = ?,
                           processed_at = CURRENT_TIMESTAMP, rejection_reason = ?
                       WHERE request_id = ?""",
                    (session.employee_id, reason, request_id),
                )
                audit_service.log(conn, "deactivation_rejected",
                                  f"Account {req['account_id']}; {reason}",
                                  employee_id=session.employee_id)
                return False, f"Rejected: {reason}"

            conn.execute(
                """UPDATE accounts_db.accounts
                   SET status = 'deactivated', updated_at = CURRENT_TIMESTAMP
                   WHERE account_id = ?""",
                (req["account_id"],),
            )
            conn.execute(
                """UPDATE requests_db.deactivations
                   SET status = 'approved', processed_by = ?, processed_at = CURRENT_TIMESTAMP
                   WHERE request_id = ?""",
                (session.employee_id, request_id),
            )
            audit_service.log(conn, "deactivation_approved",
                              f"Account {req['account_id']}", employee_id=session.employee_id)
            return True, "Approved: account deactivated"

    def reject_deactivation(self, session: EmployeeSession, request_id: int, reason: str) -> None:
        if not reason.strip():
            raise ValueError("A rejection reason is required")
        with transaction() as conn:
            require_role(conn, session, "accountant")
            req = conn.execute(
                "SELECT account_id FROM requests_db.deactivations "
                "WHERE request_id = ? AND status = 'pending'", (request_id,)
            ).fetchone()
            if req is None:
                raise ValueError("Pending deactivation request not found")
            conn.execute(
                """UPDATE requests_db.deactivations
                   SET status = 'rejected', processed_by = ?,
                       processed_at = CURRENT_TIMESTAMP, rejection_reason = ?
                   WHERE request_id = ?""",
                (session.employee_id, reason.strip(), request_id),
            )
            audit_service.log(conn, "deactivation_rejected",
                              f"Account {req['account_id']}; Reason: {reason.strip()}",
                              employee_id=session.employee_id)


request_service = RequestService()
