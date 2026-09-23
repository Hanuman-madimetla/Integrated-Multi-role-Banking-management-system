from __future__ import annotations

import sqlite3
from typing import Optional

from .audit_service import audit_service
from .db import read_only, transaction
from .permissions import EmployeeSession, require_role
from .security import hash_password, needs_rehash, verify_password


class AccountService:
    # ------------------------------------------------------------ lookups
    def get_by_id(self, account_id: int) -> Optional[sqlite3.Row]:
        with read_only() as conn:
            return conn.execute(
                "SELECT * FROM accounts_db.accounts WHERE account_id = ?", (account_id,)
            ).fetchone()

    def get_by_username(self, username: str) -> Optional[sqlite3.Row]:
        with read_only() as conn:
            return conn.execute(
                "SELECT * FROM accounts_db.accounts WHERE username = ?", (username,)
            ).fetchone()

    def list_accounts(self, session: EmployeeSession) -> list[sqlite3.Row]:
        with read_only() as conn:
            require_role(conn, session, "manager")
            return conn.execute(
                """SELECT account_id, customer_id, username, balance_paise, status
                   FROM accounts_db.accounts ORDER BY account_id"""
            ).fetchall()

    # ------------------------------------------------------ customer login
    def authenticate_customer(self, username: str, password: str) -> Optional[sqlite3.Row]:
        """
        Returns the account row for correct credentials (any status, so a
        deactivated customer can still see their deactivation result).
        The caller must check account['status'] before allowing banking.
        """
        with transaction() as conn:
            acc = conn.execute(
                "SELECT * FROM accounts_db.accounts WHERE username = ?", (username,)
            ).fetchone()

            if acc is None or not verify_password(password, acc["password_hash"]):
                audit_service.log(conn, "customer_login_failed", f"Username: {username}",
                                  actor=f"customer:{username}")
                return None

            if needs_rehash(acc["password_hash"]):
                conn.execute(
                    "UPDATE accounts_db.accounts SET password_hash = ? WHERE account_id = ?",
                    (hash_password(password), acc["account_id"]),
                )
                acc = conn.execute(
                    "SELECT * FROM accounts_db.accounts WHERE account_id = ?",
                    (acc["account_id"],),
                ).fetchone()
            audit_service.log(conn, "customer_login", f"Account {acc['account_id']}",
                              actor=f"customer:{username}")
            return acc

    def change_credentials(self, account_id: int, current_password: str,
                           new_username: Optional[str] = None,
                           new_password: Optional[str] = None) -> sqlite3.Row:
        """Atomically change one or both customer credentials."""
        if new_username is None and new_password is None:
            raise ValueError("Provide a new username or password")
        if new_password is not None and len(new_password) < 6:
            raise ValueError("Password must have at least 6 characters")
        username = new_username.strip() if new_username is not None else None
        if new_username is not None and not username:
            raise ValueError("Username is required")

        with transaction() as conn:
            account = conn.execute(
                "SELECT * FROM accounts_db.accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
            if account is None:
                raise ValueError("Account not found")
            if not verify_password(current_password, account["password_hash"]):
                raise ValueError("Current password is incorrect")
            if username is not None and username != account["username"]:
                if conn.execute(
                    "SELECT 1 FROM accounts_db.accounts WHERE username = ? AND account_id != ?",
                    (username, account_id),
                ).fetchone() or conn.execute(
                    "SELECT 1 FROM requests_db.registrations WHERE username = ?",
                    (username,),
                ).fetchone():
                    raise ValueError("Username is already in use")

            fields, values = [], []
            if username is not None:
                fields.append("username = ?")
                values.append(username)
            if new_password is not None:
                fields.append("password_hash = ?")
                values.append(hash_password(new_password))
            fields.append("updated_at = CURRENT_TIMESTAMP")
            values.append(account_id)
            conn.execute(
                f"UPDATE accounts_db.accounts SET {', '.join(fields)} WHERE account_id = ?",
                values,
            )
            audit_service.log(
                conn, "customer_credentials_changed",
                f"Account {account_id}",
                actor=f"customer:{username or account['username']}",
            )
            return conn.execute(
                "SELECT * FROM accounts_db.accounts WHERE account_id = ?", (account_id,)
            ).fetchone()

    def change_username(self, account_id: int, current_password: str,
                        new_username: str) -> sqlite3.Row:
        return self.change_credentials(account_id, current_password,
                                       new_username=new_username)

    def change_password(self, account_id: int, current_password: str,
                        new_password: str) -> sqlite3.Row:
        return self.change_credentials(account_id, current_password,
                                       new_password=new_password)

    update_username = change_username
    update_password = change_password
    change_customer_credentials = change_credentials

    # -------------------------------------------------------- registration
    def submit_registration(self, customer_id: str, username: str,
                            customer_name: str, password: str) -> int:
        customer_id, username, customer_name = (
            customer_id.strip(), username.strip(), customer_name.strip()
        )
        if not customer_id or not username or not customer_name:
            raise ValueError("Customer ID, username and full name are required")
        if len(password) < 6:
            raise ValueError("Password must have at least 6 characters")

        with transaction() as conn:
            if conn.execute(
                "SELECT 1 FROM requests_db.registrations WHERE customer_id = ? OR username = ?",
                (customer_id, username),
            ).fetchone():
                raise ValueError("A registration already exists for this ID or username")

            if conn.execute(
                "SELECT 1 FROM accounts_db.accounts WHERE customer_id = ? OR username = ?",
                (customer_id, username),
            ).fetchone():
                raise ValueError("A customer account already exists")

            cur = conn.execute(
                """INSERT INTO requests_db.registrations
                   (customer_id, username, customer_name, password_hash)
                   VALUES (?, ?, ?, ?)""",
                (customer_id, username, customer_name, hash_password(password)),
            )
            audit_service.log(conn, "registration_submitted", f"Customer {customer_id}",
                              actor=f"customer:{username}")
            return int(cur.lastrowid)

    def get_registration_status(self, customer_id: str) -> Optional[dict]:
        """Internal / already-authenticated use."""
        with read_only() as conn:
            row = conn.execute(
                """SELECT r.*, a.account_id, a.status AS account_status
                   FROM requests_db.registrations r
                   LEFT JOIN accounts_db.accounts a ON a.customer_id = r.customer_id
                   WHERE r.customer_id = ?""",
                (customer_id,),
            ).fetchone()
            return dict(row) if row else None

    def lookup_registration_status(self, customer_id: str, password: str) -> Optional[dict]:
        """Public lookup: customer ID + password, so nobody can snoop on other IDs."""
        status = self.get_registration_status(customer_id.strip())
        if status is None or not verify_password(password, status["password_hash"]):
            return None
        status.pop("password_hash", None)
        return status

    # -------------------------------------------------------- deactivation
    def submit_deactivation(self, account_id: int, reason: str) -> int:
        with transaction() as conn:
            acc = conn.execute(
                "SELECT * FROM accounts_db.accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
            if acc is None:
                raise ValueError("Account not found")
            if acc["status"] != "active":
                raise ValueError("Account is not active")
            if conn.execute(
                """SELECT 1 FROM requests_db.deactivations
                   WHERE account_id = ? AND status = 'pending'""",
                (account_id,),
            ).fetchone():
                raise ValueError("A deactivation request is already pending")

            cur = conn.execute(
                "INSERT INTO requests_db.deactivations(account_id, reason) VALUES (?, ?)",
                (account_id, reason.strip()),
            )
            audit_service.log(conn, "deactivation_requested", f"Account {account_id}",
                              actor=f"customer:{acc['username']}")
            return int(cur.lastrowid)

    def get_deactivation_status(self, account_id: int) -> Optional[dict]:
        with read_only() as conn:
            row = conn.execute(
                """SELECT d.request_id, d.status, d.rejection_reason, a.status AS account_status
                   FROM requests_db.deactivations d
                   JOIN accounts_db.accounts a ON a.account_id = d.account_id
                   WHERE d.account_id = ?
                   ORDER BY d.request_id DESC LIMIT 1""",
                (account_id,),
            ).fetchone()
            return dict(row) if row else None


account_service = AccountService()
