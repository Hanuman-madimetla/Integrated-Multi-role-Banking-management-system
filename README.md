Banking Management System

One-line tagline

A role-based banking system simulating real-world customer and employee banking workflows using Python and SQLite.

Core features

Customer Ecosystem

Customer registration and registration-status tracking
Secure customer authentication
Balance management
Deposits and withdrawals
Account-to-account transfers
Transaction history
Credential management
Account deactivation requests

Employee Ecosystem

Manager — employee management, suspension/activation, account and transaction monitoring, audit logs
Field Officer — registration verification/rejection
Accountant — registration approval/rejection and account lifecycle processing
Cashier — deposits, withdrawals, account lookup and transaction history

Security & Architecture

Role-based access control enforced at the service layer
PBKDF2-HMAC-SHA256 password hashing with salted credentials
Automatic migration from legacy password hashes
Atomic database transactions
Integer-paise monetary representation to avoid floating-point money errors
Transaction-level balance validation
Audit logging for important operations
Input validation and controlled error handling
Registration workflow
Customer
   ↓
Registration Request
   ↓
Field Officer
   ├── Reject
   └── Verify
         ↓
      Accountant
       ├── Reject
       └── Approve
              ↓
        Bank Account Created
Account deactivation workflow
Customer
   ↓
Deactivation Request
   ↓
Accountant
   ↓
Balance Check
   ├── Balance > ₹0 → Rejected
   └── Balance = ₹0 → Account Deactivated
Architecture

Your code has a nice separation:

bank_system/
│
├── bank_core/
│   ├── account_service.py
│   ├── audit_service.py
│   ├── db.py
│   ├── employee_service.py
│   ├── money.py
│   ├── permissions.py
│   ├── request_service.py
│   ├── security.py
│   └── transaction_service.py
│
├── dashboards/
│   ├── manager.py
│   ├── accountant.py
│   ├── cashier.py
│   └── field_officer.py
│
├── customer_app.py
├── employee_login.py
├── main.py
└── ui.py
