from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).resolve().parent.parent
ACCOUNTS_DB = BASE_DIR / "accounts.db"
REQUESTS_DB = BASE_DIR / "requests.db"
EMPLOYEES_DB = BASE_DIR / "employees.db"


def _open() -> sqlite3.Connection:
    # isolation_level=None -> we control BEGIN/COMMIT/ROLLBACK ourselves.
    conn = sqlite3.connect(str(EMPLOYEES_DB), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("ATTACH DATABASE ? AS accounts_db", (str(ACCOUNTS_DB),))
    conn.execute("ATTACH DATABASE ? AS requests_db", (str(REQUESTS_DB),))
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """
    One atomic unit of work across employees.db, accounts.db and requests.db.
    Any exception rolls EVERYTHING back (money, request status, audit log).
    """
    conn = _open()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


@contextmanager
def read_only() -> Iterator[sqlite3.Connection]:
    conn = _open()
    try:
        yield conn
    finally:
        conn.close()


def _ensure_column(conn, schema: str, table: str, column: str, definition: str) -> None:
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA {schema}.table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {schema}.{table} ADD COLUMN {column} {definition}")


def initialize_databases() -> None:
    conn = _open()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS employees (
                employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (
                    role IN ('cashier','field_officer','accountant','manager')
                ),
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active','suspended')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER,
                actor TEXT,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(employee_id) REFERENCES employees(employee_id)
            );

            CREATE TABLE IF NOT EXISTS accounts_db.accounts (
                account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE NOT NULL,
                customer_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                balance_paise INTEGER NOT NULL DEFAULT 0 CHECK(balance_paise >= 0),
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active','deactivated')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS accounts_db.transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('deposit','withdrawal','transfer')),
                amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
                balance_after_paise INTEGER,
                performed_by TEXT NOT NULL,
                timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(account_id) REFERENCES accounts(account_id)
            );

            CREATE TABLE IF NOT EXISTS requests_db.registrations (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE NOT NULL,
                customer_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','verified','approved','rejected')),
                submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                verified_by INTEGER,
                verified_at TEXT,
                approved_by INTEGER,
                approved_at TEXT,
                rejected_by INTEGER,
                rejected_at TEXT,
                rejection_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS requests_db.deactivations (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','approved','rejected')),
                submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                processed_by INTEGER,
                processed_at TEXT,
                rejection_reason TEXT
            );
            """
        )

        # ---- migrations for databases created by older phases ----
        # (ALTER TABLE can only add columns with constant defaults.)
        _ensure_column(conn, "accounts_db", "accounts", "customer_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "accounts_db", "accounts", "balance_paise", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "accounts_db", "transactions", "performed_by", "TEXT NOT NULL DEFAULT 'system'")
        _ensure_column(conn, "accounts_db", "transactions", "amount_paise", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "accounts_db", "transactions", "balance_after_paise", "INTEGER")
        _ensure_column(conn, "requests_db", "registrations", "rejected_by", "INTEGER")
        _ensure_column(conn, "requests_db", "registrations", "rejected_at", "TEXT")
        _ensure_column(conn, "requests_db", "deactivations", "processed_at", "TEXT")
        _ensure_column(conn, "requests_db", "deactivations", "rejection_reason", "TEXT")
        _ensure_column(conn, "main", "audit_logs", "actor", "TEXT")

        # Convert old REAL rupee balances to integer paise (one-time).
        cols = {r["name"] for r in conn.execute("PRAGMA accounts_db.table_info(accounts)")}
        if "balance" in cols:
            conn.execute(
                """UPDATE accounts_db.accounts
                   SET balance_paise = CAST(ROUND(balance * 100) AS INTEGER)
                   WHERE balance_paise = 0 AND balance <> 0"""
            )
        tcols = {r["name"] for r in conn.execute("PRAGMA accounts_db.table_info(transactions)")}
        if "amount" in tcols:
            conn.execute(
                """UPDATE accounts_db.transactions
                   SET amount_paise = CAST(ROUND(amount * 100) AS INTEGER)
                   WHERE amount_paise = 0 AND amount <> 0"""
            )
    finally:
        conn.close()
