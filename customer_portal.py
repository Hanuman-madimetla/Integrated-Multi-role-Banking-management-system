"""Standalone customer portal launcher."""
from bank_core import initialize_databases
from customer_app import customer_login, customer_registration, show_registration_status_public


def main() -> None:
    initialize_databases()
    while True:
        print("\n=== CUSTOMER PORTAL ===")
        print("1. Customer login\n2. Register customer account\n3. Check registration status\n4. Exit")
        choice = input("Select: ").strip()
        if choice == "1":
            customer_login()
        elif choice == "2":
            customer_registration()
        elif choice == "3":
            show_registration_status_public()
        elif choice == "4":
            return
        else:
            print("Invalid option.")


if __name__ == "__main__":
    main()
