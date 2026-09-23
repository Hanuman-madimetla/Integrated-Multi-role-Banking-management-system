from bank_core import request_service
from bank_core.permissions import EmployeeSession
from ui import HANDLED_ERRORS, ask_int, header


def field_officer_dashboard(session: EmployeeSession) -> None:
    while True:
        header("Field Officer Dashboard", session)
        print("1. View pending registrations\n2. Verify registration\n"
              "3. Reject registration\n4. Logout")
        choice = input("Select: ").strip()

        try:
            if choice == "1":
                rows = request_service.list_pending_registrations(session)
                if not rows:
                    print("No pending registrations.")
                for r in rows:
                    print(f"Request {r['request_id']} | {r['customer_id']} | "
                          f"{r['customer_name']} | {r['submitted_at']}")

            elif choice == "2":
                request_service.verify_registration(session, ask_int("Request ID: "))
                print("Registration verified. Sent to the accountant.")

            elif choice == "3":
                request_service.reject_registration(
                    session, ask_int("Request ID: "), input("Reason: "))
                print("Registration rejected.")

            elif choice == "4":
                return
            else:
                print("Invalid option.")
        except HANDLED_ERRORS as error:
            print(f"Error: {error}")
