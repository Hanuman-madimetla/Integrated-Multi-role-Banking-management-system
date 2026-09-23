"""8.1 Employee login controller: the single entry point for the employee side."""
from getpass import getpass

from bank_core import employee_service
from dashboards import DASHBOARDS


def employee_login() -> None:
    username = input("Employee username: ").strip()
    password = getpass("Employee password: ")

    session = employee_service.authenticate(username, password)
    if session is None:
        print("Invalid employee credentials or suspended account.")
        return

    dashboard = DASHBOARDS.get(session.role)
    if dashboard is None:
        print("No dashboard is configured for this role.")
        return

    print(f"\nWelcome, {session.username} ({session.role.replace('_', ' ')}).")
    try:
        dashboard(session)          # receives employee_id, username, role
    finally:
        employee_service.logout(session)
