"""Standalone employee portal launcher."""
from getpass import getpass

from bank_core import employee_service, initialize_databases
from employee_login import employee_login


def first_run_setup() -> None:
    if employee_service.count() > 0:
        return
    print("No employees exist yet. Create the first manager account.")
    while True:
        try:
            employee_service.bootstrap_first_manager(
                input("Manager username: ").strip(), getpass("Manager password: "))
            print("Manager created.")
            return
        except ValueError as error:
            print(f"Error: {error}")


def main() -> None:
    initialize_databases()
    first_run_setup()
    employee_login()


if __name__ == "__main__":
    main()
