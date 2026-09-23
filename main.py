from getpass import getpass

from bank_core import employee_service, initialize_databases
from customer_app import (customer_login, customer_registration,
                          show_registration_status_public)
from employee_login import employee_login


def first_run_setup() -> None:
    if employee_service.count() > 0:
        return
    print("No employees exist yet. Create the first manager account.")
    while True:
        try:
            employee_service.bootstrap_first_manager(
                input("Manager username: ").strip(), getpass("Manager password: "))
            print("Manager created. Log in through 'Employee login' to add staff.")
            return
        except ValueError as error:
            print(f"Error: {error}")


def main() -> None:
    initialize_databases()
    first_run_setup()

    while True:
        print("\n==============================\n        BANK SYSTEM\n==============================")
        print("1. Employee login\n2. Customer login\n3. Register customer account\n"
              "4. Check registration status\n5. Exit")
        choice = input("Select: ").strip()

        if choice == "1":
            employee_login()
        elif choice == "2":
            customer_login()
        elif choice == "3":
            customer_registration()
        elif choice == "4":
            show_registration_status_public()
        elif choice == "5":
            print("Goodbye.")
            break
        else:
            print("Invalid option.")


if __name__ == "__main__":
    main()
