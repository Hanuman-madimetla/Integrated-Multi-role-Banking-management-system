from getpass import getpass

from bank_core import audit_service, account_service, employee_service, format_paise, transaction_service
from bank_core.employee_service import ROLES
from bank_core.permissions import EmployeeSession
from ui import HANDLED_ERRORS, ask_int, header


def manager_dashboard(session: EmployeeSession) -> None:
    while True:
        header("Manager Dashboard", session)
        print("1. Employees\n2. Add employee\n3. Suspend / activate employee\n"
              "4. Audit logs\n5. Accounts\n6. Transactions\n7. Logout")
        choice = input("Select: ").strip()

        try:
            if choice == "1":
                for e in employee_service.list_employees(session):
                    print(f"{e['employee_id']} | {e['username']} | {e['role']} | {e['status']}")

            elif choice == "2":
                username = input("New username: ").strip()
                role = input(f"Role ({', '.join(ROLES)}): ").strip()
                employee_service.create_employee(session, username, getpass("Password: "), role)
                print("Employee created.")

            elif choice == "3":
                emp_id = ask_int("Employee ID: ")
                status = input("New status (active/suspended): ").strip()
                employee_service.set_status(session, emp_id, status)
                print("Status updated.")

            elif choice == "4":
                for l in audit_service.recent(session):
                    print(f"{l['log_id']} | {l['timestamp']} | {l['who']} | "
                          f"{l['action']} | {l['details']}")

            elif choice == "5":
                for a in account_service.list_accounts(session):
                    print(f"Account {a['account_id']} | {a['customer_id']} | {a['username']} | "
                          f"{format_paise(a['balance_paise'])} | {a['status']}")

            elif choice == "6":
                for t in transaction_service.recent(session):
                    print(f"Txn {t['transaction_id']} | Acc {t['account_id']} | {t['type']} | "
                          f"{format_paise(t['amount_paise'])} | {t['performed_by']} | {t['timestamp']}")

            elif choice == "7":
                return
            else:
                print("Invalid option.")
        except HANDLED_ERRORS as error:
            print(f"Error: {error}")
