from bank_core import account_service, format_paise, transaction_service
from bank_core.permissions import EmployeeSession
from ui import HANDLED_ERRORS, ask_int, header


def cashier_dashboard(session: EmployeeSession) -> None:
    while True:
        header("Cashier Dashboard", session)
        print("1. Deposit\n2. Withdraw\n3. Search account\n4. Transaction history\n5. Logout")
        choice = input("Select: ").strip()

        try:
            if choice == "1":
                r = transaction_service.cashier_deposit(
                    session, ask_int("Account ID: "), input("Amount in rupees: "))
                print(f"Deposit done. Transaction ID: {r.transaction_id} | "
                      f"New balance: {format_paise(r.balance_after_paise)}")

            elif choice == "2":
                r = transaction_service.cashier_withdraw(
                    session, ask_int("Account ID: "), input("Amount in rupees: "))
                print(f"Withdrawal done. Transaction ID: {r.transaction_id} | "
                      f"New balance: {format_paise(r.balance_after_paise)}")

            elif choice == "3":
                acc = account_service.get_by_username(input("Customer username: ").strip())
                if acc is None:
                    print("Account not found.")
                else:
                    print(f"Account ID: {acc['account_id']} | {acc['customer_name']} | "
                          f"{format_paise(acc['balance_paise'])} | {acc['status']}")

            elif choice == "4":
                for t in transaction_service.history(ask_int("Account ID: ")):
                    print(f"Txn {t['transaction_id']} | {t['type']} | "
                          f"{format_paise(t['amount_paise'])} | "
                          f"balance {format_paise(t['balance_after_paise'] or 0)} | "
                          f"{t['performed_by']} | {t['timestamp']}")

            elif choice == "5":
                return
            else:
                print("Invalid option.")
        except HANDLED_ERRORS as error:
            print(f"Error: {error}")
