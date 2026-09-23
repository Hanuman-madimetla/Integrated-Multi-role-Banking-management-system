"""Customer side. Uses the same services as the employee side, and never
reveals which employee handled a request."""
from getpass import getpass
import sqlite3

from bank_core import account_service, format_paise, request_service, transaction_service
from ui import HANDLED_ERRORS, header


def customer_registration() -> None:
    try:
        request_id = account_service.submit_registration(
            input("Customer ID: "), input("Username: "),
            input("Full name: "), getpass("Password: "),
        )
        print(f"Registration submitted. Request ID: {request_id}")
        print("Use 'Check registration status' to follow its progress.")
    except HANDLED_ERRORS as error:
        print(f"Registration failed: {error}")


def _print_registration_status(r: dict) -> None:
    status = r["status"]
    verified = bool(r["verified_by"])

    if verified:
        officer = "✓ Verified"
    elif status == "rejected":
        officer = "✗ Rejected"
    else:
        officer = "⏳ Pending"

    if status == "approved":
        accountant = "✓ Approved"
    elif status == "rejected" and verified:
        accountant = "✗ Rejected"
    elif status == "verified":
        accountant = "⏳ Pending"
    else:
        accountant = "— Waiting for verification"

    print("\n=== Account Registration ===")
    print(f"Customer ID: {r['customer_id']}")
    print(f"Status: {'ACTIVE' if status == 'approved' and r['account_status'] == 'active' else status.upper()}")
    print(f"Field Officer: {officer}")
    print(f"Accountant: {accountant}")

    if status == "pending":
        print("Your registration is awaiting verification.")
    elif status == "verified":
        print("Your account is awaiting final approval.")
    elif status == "approved":
        print(f"Account ID: {r['account_id']}")
        print(f"Account Status: {r['account_status'].upper()}")
        print("You can now log in.")
    elif status == "rejected":
        print(f"Reason: {r['rejection_reason']}")


def show_registration_status_public() -> None:
    r = account_service.lookup_registration_status(
        input("Customer ID: "), getpass("Password: "))
    if r is None:
        print("No registration found for those details.")
    else:
        _print_registration_status(r)


def show_deactivation_status(account_id: int) -> None:
    d = account_service.get_deactivation_status(account_id)
    if d is None:
        print("No deactivation request found.")
        return
    print("\n=== Deactivation Request ===")
    print(f"Status: {d['status'].upper()}")
    print(f"Account Status: {d['account_status'].upper()}")
    if d["status"] == "rejected" and d["rejection_reason"]:
        print(f"Reason: {d['rejection_reason']}")


def change_credentials(account: sqlite3.Row) -> sqlite3.Row:
    current = getpass("Current password: ")
    print("1. Change username\n2. Change password\n3. Change both")
    choice = input("Select: ").strip()
    username = password = None
    if choice in ("1", "3"):
        username = input("New username: ").strip()
    if choice in ("2", "3"):
        password = getpass("New password: ")
        if password != getpass("Confirm new password: "):
            raise ValueError("Passwords do not match")
    if choice not in ("1", "2", "3"):
        raise ValueError("Invalid option")
    updated = account_service.change_credentials(
        account["account_id"], current, username, password)
    print("Credentials updated.")
    return updated


def customer_login() -> None:
    account = account_service.authenticate_customer(
        input("Customer username: ").strip(), getpass("Customer password: "))

    if account is None:
        print("Invalid credentials.")
        return

    if account["status"] != "active":
        print("\nThis account has been DEACTIVATED.")
        show_deactivation_status(account["account_id"])
        return

    customer_dashboard(account)


def profile_settings(account: sqlite3.Row) -> None:
    while True:
        print("\n=== Profile Settings ===")
        print("1. Account Details\n2. Change Credentials\n3. Request Deactivation\n"
              "4. Registration Status\n5. Deactivation Status\n6. Back")
        choice = input("Select: ").strip()

        try:
            if choice == "1":
                current = account_service.get_by_id(account["account_id"])
                print(f"Account ID: {current['account_id']}")
                print(f"Customer ID: {current['customer_id']}")
                print(f"Username: {current['username']}")
                print(f"Account Status: {current['status'].upper()}")
                print(f"Balance: {format_paise(current['balance_paise'])}")

            elif choice == "2":
                account = change_credentials(account)

            elif choice == "3":
                reason = input("Reason for deactivation: ").strip() or "Requested by customer"
                request_id = account_service.submit_deactivation(account["account_id"], reason)
                print(f"Deactivation request submitted. Request ID: {request_id}")

            elif choice == "4":
                registration = account_service.get_registration_status(account["customer_id"])
                if registration:
                    _print_registration_status(registration)
                else:
                    print("No registration record found.")

            elif choice == "5":
                show_deactivation_status(account["account_id"])

            elif choice == "6":
                return
            else:
                print("Invalid option.")
        except HANDLED_ERRORS as error:
            print(f"Error: {error}")


def customer_dashboard(account: sqlite3.Row) -> None:
    account_id = account["account_id"]
    while True:
        header(f"Customer Dashboard - {account['customer_name']}")
        print("1. View balance\n2. Transfer\n3. Transaction History\n4. Profile Settings\n5. Logout")
        choice = input("Select: ").strip()

        try:
            if choice == "1":
                current = account_service.get_by_id(account_id)
                print(f"Balance: {format_paise(current['balance_paise'])}")

            elif choice == "2":
                recipient_username = input("Recipient username: ").strip()
                recipient = account_service.get_by_username(recipient_username)
                if recipient is None:
                    raise ValueError("Recipient account not found")
                sent, _ = transaction_service.customer_transfer(
                    account,
                    recipient["account_id"],
                    input("Amount in rupees: "),
                )
                print(f"Transfer complete. Reference: {sent.transaction_id} | "
                      f"Balance: {format_paise(sent.balance_after_paise)}")

            elif choice == "3":
                for t in transaction_service.history(account_id):
                    print(f"Ref {t['transaction_id']} | {t['type']} | "
                          f"{format_paise(t['amount_paise'])} | {t['timestamp']}")

            elif choice == "4":
                profile_settings(account)

            elif choice == "5":
                return
            else:
                print("Invalid option.")
        except HANDLED_ERRORS as error:
            print(f"Error: {error}")
