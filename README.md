# Bank System

This is a standard-library Python banking prototype with two separate
front-end ecosystems connected to one shared bank core:

- **Customer side**: registration, registration-status tracking, customer login,
  balance viewing, transfers, transaction history, profile settings, and
  deactivation requests.
- **Employee side**: one employee login controller that routes to the cashier,
  field-officer, accountant, or manager dashboard.

## Requirements

- Python 3.10 or newer
- No third-party packages

## Run locally

```powershell
cd C:\path\to\bank_system
python customer_portal.py   # customer-only portal
python employee_portal.py   # employee-only portal
python main.py               # optional combined convenience launcher
```

On Windows, the equivalent double-click launchers are `run_customer.bat`,
`run_employee.bat`, and `run_bank.bat`.

The customer launcher imports only customer-facing UI and shared
`bank_core` services; it does not import or expose employee dashboards.
Both portals use the same attached SQLite databases and service layer.

The application uses only Python's standard library. On first run it creates
the three SQLite databases and asks for the first manager account. The manager
can then create the remaining employee accounts.

## Final zip-ready structure

```text
bank_system/
├── README.md
├── requirements.txt
├── .gitignore
├── run_bank.bat
├── run_customer.bat
├── run_employee.bat
├── main.py                    Optional combined launcher
├── customer_portal.py         Customer-only entry point
├── employee_portal.py         Employee-only entry point
├── customer_app.py            Customer-facing workflows
├── employee_login.py          Employee authentication/controller
├── ui.py                      Shared terminal UI helpers
├── bank_core/
│   ├── account_service.py       Customer accounts and registration submission
│   ├── audit_service.py         Central employee/customer audit trail
│   ├── db.py                    Attached SQLite connections and migrations
│   ├── employee_service.py     Employee authentication and administration
│   ├── money.py                  Integer-paise conversion and formatting
│   ├── permissions.py            Server-side role enforcement
│   ├── request_service.py       Registration and deactivation workflows
│   ├── security.py               Password hashing and verification
│   └── transaction_service.py   Shared atomic deposit/withdrawal service
├── dashboards/
│   ├── cashier.py
│   ├── field_officer.py
│   ├── accountant.py
│   └── manager.py
└── tests/
    ├── __init__.py
    └── test_workflows.py
```

The following files are intentionally not included in a release zip:
`accounts.db`, `requests.db`, `employees.db`, `__pycache__/`, and
`.pytest_cache/`. They are generated locally at first startup and may contain
private customer or employee data.

## Workflow

### Employee login

`employee_portal.py` calls `employee_login.py`. Successful authentication creates an
`EmployeeSession(employee_id, username, role)`. The role selects exactly one
dashboard, and every dashboard receives the complete session instead of only a
username. Services repeat the role check against `employees.db` before every
privileged operation.

### Customer registration

```text
Customer
  -> bank_core.account_service.submit_registration()
  -> requests.db: pending
  -> field_officer dashboard: verify
  -> requests.db: verified
  -> accountant dashboard: approve
  -> accounts.db: active account
  -> customer login becomes available
```

Account creation and final request approval are committed in the same
transaction. If either operation fails, both are rolled back.

### Registration status

Customers can query their request with customer ID and password. The UI shows
the field-officer stage, accountant stage, request status, account ID, and
active/deactivated account status without exposing employee details.

### Deactivation

```text
Customer
  -> requests.db: pending
  -> accountant checks accounts.db balance
       balance > 0  -> requests.db: rejected
       balance = 0  -> accounts.db: deactivated
                         requests.db: approved
```

Deactivation status remains visible after the customer logs in, including for
an account that is no longer active.

### Transactions

Both cashier and customer/ATM operations call
`bank_core.transaction_service.TransactionService`. No dashboard updates a
balance directly. Each operation:

1. Validates the amount.
2. Converts rupees to integer paise.
3. Updates the balance and inserts a transaction record atomically.
4. Records the transaction ID, actor, resulting balance, and audit event.

This prevents floating-point money errors and prevents withdrawals from
creating negative balances.

## Databases

The application creates these files beside `main.py`:

- `employees.db`: employees and audit logs
- `requests.db`: registration and deactivation requests
- `accounts.db`: customer accounts and financial transactions

`bank_core.db` attaches all three databases to one SQLite connection so
cross-database workflows can commit or roll back together.
