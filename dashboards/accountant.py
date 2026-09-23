from bank_core import format_paise, request_service
from bank_core.permissions import EmployeeSession
from ui import HANDLED_ERRORS, ask_int, header


def accountant_dashboard(session: EmployeeSession) -> None:
    while True:
        header("Accountant Dashboard", session)
        print("1. View verified registrations\n2. Approve registration\n"
              "3. Reject registration\n4. View deactivation requests\n"
              "5. Process deactivation (balance check)\n6. Reject deactivation\n7. Logout")
        choice = input("Select: ").strip()

        try:
            if choice == "1":
                rows = request_service.list_verified_registrations(session)
                if not rows:
                    print("Nothing awaiting approval.")
                for r in rows:
                    print(f"Request {r['request_id']} | {r['customer_id']} | "
                          f"{r['customer_name']} | verified {r['verified_at']}")

            elif choice == "2":
                account_id = request_service.approve_registration(session, ask_int("Request ID: "))
                print(f"Account created. Account ID: {account_id}")

            elif choice == "3":
                request_service.reject_registration(
                    session, ask_int("Request ID: "), input("Reason: "))
                print("Registration rejected.")

            elif choice == "4":
                rows = request_service.list_pending_deactivations(session)
                if not rows:
                    print("No pending deactivation requests.")
                for r in rows:
                    print(f"Request {r['request_id']} | Account {r['account_id']} | "
                          f"{r['username']} | Balance {format_paise(r['balance_paise'])} | "
                          f"Reason: {r['reason']}")

            elif choice == "5":
                _, message = request_service.process_deactivation(session, ask_int("Request ID: "))
                print(message)

            elif choice == "6":
                request_service.reject_deactivation(
                    session, ask_int("Request ID: "), input("Reason: "))
                print("Deactivation rejected.")

            elif choice == "7":
                return
            else:
                print("Invalid option.")
        except HANDLED_ERRORS as error:
            print(f"Error: {error}")
