from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

from .audit_service import audit_service
from .db import read_only, transaction
from .money import format_paise, rupees_to_paise
from .permissions import EmployeeSession, require_role


@dataclass(frozen=True)
class Receipt:
    transaction_id: int
    account_id: int
    kind: str
    amount_paise: int
    balance_after_paise: int


class TransactionService:
    """
    The ONLY place that changes a balance. The cashier dashboard and the
    customer/ATM app both call it, so both sides share the same rules.
    """

    # ------------------------------------------------------ cashier side
    def cashier_deposit(self, session: EmployeeSession, account_id: int, amount) -> Receipt:
        return self._post("deposit", account_id, amount, session=session)

    def cashier_withdraw(self, session: EmployeeSession, account_id: int, amount) -> Receipt:
        return self._post("withdrawal", account_id, amount, session=session)

    # ----------------------------------------------------- customer side
    def customer_deposit(self, account: sqlite3.Row, amount) -> Receipt:
        return self._post("deposit", account["account_id"], amount,
                          customer=account["username"])

    def customer_withdraw(self, account: sqlite3.Row, amount) -> Receipt:
        return self._post("withdrawal", account["account_id"], amount,
                          customer=account["username"])

    def customer_transfer(self, account: sqlite3.Row, recipient_account_id: int,
                          amount) -> tuple[Receipt, Receipt]:
        """Transfer paise atomically and record a row for each account."""
        amount_paise = rupees_to_paise(amount)
        source_id = account["account_id"]
        with transaction() as conn:
            source = conn.execute(
                "SELECT * FROM accounts_db.accounts WHERE account_id = ?", (source_id,)
            ).fetchone()
            if isinstance(recipient_account_id, sqlite3.Row):
                target = conn.execute(
                    "SELECT * FROM accounts_db.accounts WHERE account_id = ?",
                    (recipient_account_id["account_id"],),
                ).fetchone()
            elif isinstance(recipient_account_id, str):
                target = conn.execute(
                    "SELECT * FROM accounts_db.accounts WHERE username = ?",
                    (recipient_account_id.strip(),),
                ).fetchone()
            else:
                target = conn.execute(
                    "SELECT * FROM accounts_db.accounts WHERE account_id = ?",
                    (recipient_account_id,),
                ).fetchone()
            if source is None or target is None:
                raise ValueError("Account not found")
            recipient_account_id = target["account_id"]
            if source["status"] != "active" or target["status"] != "active":
                raise ValueError("Both accounts must be active")
            if source_id == recipient_account_id:
                raise ValueError("Cannot transfer to the same account")
            cur = conn.execute(
                """UPDATE accounts_db.accounts
                   SET balance_paise = balance_paise - ?, updated_at = CURRENT_TIMESTAMP
                   WHERE account_id = ? AND status = 'active' AND balance_paise >= ?""",
                (amount_paise, source_id, amount_paise),
            )
            if cur.rowcount != 1:
                raise ValueError("Insufficient funds")
            conn.execute(
                """UPDATE accounts_db.accounts
                   SET balance_paise = balance_paise + ?, updated_at = CURRENT_TIMESTAMP
                   WHERE account_id = ? AND status = 'active'""",
                (amount_paise, recipient_account_id),
            )
            source_balance = conn.execute(
                "SELECT balance_paise FROM accounts_db.accounts WHERE account_id = ?",
                (source_id,),
            ).fetchone()[0]
            target_balance = conn.execute(
                "SELECT balance_paise FROM accounts_db.accounts WHERE account_id = ?",
                (recipient_account_id,),
            ).fetchone()[0]
            actor = f"customer:{source['username']}"
            source_txn = conn.execute(
                """INSERT INTO accounts_db.transactions
                   (account_id, type, amount_paise, balance_after_paise, performed_by)
                   VALUES (?, 'transfer', ?, ?, ?)""",
                (source_id, amount_paise, source_balance, actor),
            ).lastrowid
            target_txn = conn.execute(
                """INSERT INTO accounts_db.transactions
                   (account_id, type, amount_paise, balance_after_paise, performed_by)
                   VALUES (?, 'transfer', ?, ?, ?)""",
                (recipient_account_id, amount_paise, target_balance, actor),
            ).lastrowid
            details = (f"Transfer {source_id}->{recipient_account_id}; "
                       f"Amount {format_paise(amount_paise)}")
            audit_service.log(conn, "transfer_sent", details, actor=actor)
            audit_service.log(
                conn, "transfer_received",
                f"Transfer {source_id}->{recipient_account_id}; "
                f"Amount {format_paise(amount_paise)}",
                actor=actor,
            )
            return (Receipt(int(source_txn), source_id, "transfer", amount_paise, source_balance),
                    Receipt(int(target_txn), recipient_account_id, "transfer",
                            amount_paise, target_balance))

    transfer = customer_transfer
    transfer_funds = customer_transfer

    # ------------------------------------------------------------- core
    def _post(self, kind: str, account_id: int, amount,
              session: Optional[EmployeeSession] = None,
              customer: Optional[str] = None) -> Receipt:
        amount_paise = rupees_to_paise(amount)          # validation first

        with transaction() as conn:                     # atomic: all or nothing
            if session is not None:
                require_role(conn, session, "cashier")
                performed_by, employee_id, actor = session.username, session.employee_id, None
            else:
                performed_by, employee_id, actor = f"customer:{customer}", None, f"customer:{customer}"

            # The balance check lives INSIDE the UPDATE, so two simultaneous
            # withdrawals can never overdraw the account.
            if kind == "deposit":
                cur = conn.execute(
                    """UPDATE accounts_db.accounts
                       SET balance_paise = balance_paise + ?, updated_at = CURRENT_TIMESTAMP
                       WHERE account_id = ? AND status = 'active'""",
                    (amount_paise, account_id),
                )
            else:
                cur = conn.execute(
                    """UPDATE accounts_db.accounts
                       SET balance_paise = balance_paise - ?, updated_at = CURRENT_TIMESTAMP
                       WHERE account_id = ? AND status = 'active' AND balance_paise >= ?""",
                    (amount_paise, account_id, amount_paise),
                )

            if cur.rowcount != 1:
                self._raise_reason(conn, account_id)

            balance_after = conn.execute(
                "SELECT balance_paise FROM accounts_db.accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()[0]

            txn_id = conn.execute(
                """INSERT INTO accounts_db.transactions
                   (account_id, type, amount_paise, balance_after_paise, performed_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (account_id, kind, amount_paise, balance_after, performed_by),
            ).lastrowid

            audit_service.log(
                conn, kind,
                f"Transaction {txn_id}; Account {account_id}; "
                f"Amount {format_paise(amount_paise)}; Balance {format_paise(balance_after)}",
                employee_id=employee_id, actor=actor,
            )
            return Receipt(int(txn_id), account_id, kind, amount_paise, balance_after)

    @staticmethod
    def _raise_reason(conn: sqlite3.Connection, account_id: int) -> None:
        acc = conn.execute(
            "SELECT status FROM accounts_db.accounts WHERE account_id = ?", (account_id,)
        ).fetchone()
        if acc is None:
            raise ValueError("Account not found")
        if acc["status"] != "active":
            raise ValueError("Account is not active")
        raise ValueError("Insufficient funds")

    # ---------------------------------------------------------- queries
    def history(self, account_id: int, limit: int = 50) -> list[sqlite3.Row]:
        with read_only() as conn:
            return conn.execute(
                """SELECT transaction_id, type, amount_paise, balance_after_paise,
                          performed_by, timestamp
                   FROM accounts_db.transactions
                   WHERE account_id = ?
                   ORDER BY transaction_id DESC LIMIT ?""",
                (account_id, limit),
            ).fetchall()

    def recent(self, session: EmployeeSession, limit: int = 50) -> list[sqlite3.Row]:
        with read_only() as conn:
            require_role(conn, session, "manager")
            return conn.execute(
                """SELECT transaction_id, account_id, type, amount_paise,
                          performed_by, timestamp
                   FROM accounts_db.transactions
                   ORDER BY transaction_id DESC LIMIT ?""",
                (limit,),
            ).fetchall()


transaction_service = TransactionService()
