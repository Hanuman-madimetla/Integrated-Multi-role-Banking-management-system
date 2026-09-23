import shutil
import tempfile
import unittest
from pathlib import Path

from bank_core import account_service, employee_service, initialize_databases
from bank_core import request_service, transaction_service
from bank_core.db import (
    ACCOUNTS_DB,
    EMPLOYEES_DB,
    REQUESTS_DB,
)


class BankWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.original_paths = (ACCOUNTS_DB, REQUESTS_DB, EMPLOYEES_DB)

        import bank_core.db as db

        db.ACCOUNTS_DB = self.temp_dir / "accounts.db"
        db.REQUESTS_DB = self.temp_dir / "requests.db"
        db.EMPLOYEES_DB = self.temp_dir / "employees.db"
        initialize_databases()

        self.manager_id = employee_service.bootstrap_first_manager(
            "manager01",
            "manager-password",
        )
        self.manager = employee_service.authenticate(
            "manager01",
            "manager-password",
        )
        self.field_id = employee_service.create_employee(
            self.manager,
            "field01",
            "field-password",
            "field_officer",
        )
        self.field = employee_service.authenticate(
            "field01",
            "field-password",
        )
        self.accountant_id = employee_service.create_employee(
            self.manager,
            "accountant01",
            "accountant-password",
            "accountant",
        )
        self.accountant = employee_service.authenticate(
            "accountant01",
            "accountant-password",
        )
        self.cashier = employee_service.create_employee(
            self.manager,
            "cashier01",
            "cashier-password",
            "cashier",
        )
        self.cashier = employee_service.authenticate(
            "cashier01",
            "cashier-password",
        )

    def tearDown(self):
        import bank_core.db as db

        db.ACCOUNTS_DB, db.REQUESTS_DB, db.EMPLOYEES_DB = self.original_paths
        shutil.rmtree(self.temp_dir)

    def test_registration_pipeline_and_customer_login(self):
        request_id = account_service.submit_registration(
            "C1024",
            "customer01",
            "Test Customer",
            "customer-password",
        )
        pending = account_service.get_registration_status("C1024")
        self.assertEqual(pending["status"], "pending")

        request_service.verify_registration(self.field, request_id)
        verified = account_service.get_registration_status("C1024")
        self.assertEqual(verified["status"], "verified")
        self.assertIsNotNone(verified["verified_by"])

        account_id = request_service.approve_registration(
            self.accountant,
            request_id,
        )
        approved = account_service.get_registration_status("C1024")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["account_id"], account_id)

        customer = account_service.authenticate_customer(
            "customer01",
            "customer-password",
        )
        self.assertIsNotNone(customer)
        self.assertEqual(customer["status"], "active")

    def test_shared_transaction_service_uses_paise_and_audit(self):
        request_id = account_service.submit_registration(
            "C2048",
            "customer02",
            "Second Customer",
            "customer-password",
        )
        request_service.verify_registration(self.field, request_id)
        account_id = request_service.approve_registration(
            self.accountant,
            request_id,
        )

        deposit = transaction_service.cashier_deposit(
            self.cashier,
            account_id,
            "100.50",
        )
        self.assertEqual(deposit.amount_paise, 10050)
        self.assertEqual(deposit.balance_after_paise, 10050)

        withdrawal = transaction_service.customer_withdraw(
            account_service.authenticate_customer(
                "customer02",
                "customer-password",
            ),
            "0.50",
        )
        self.assertEqual(withdrawal.balance_after_paise, 10000)

        with self.assertRaises(ValueError):
            transaction_service.customer_withdraw(
                account_service.authenticate_customer(
                    "customer02",
                    "customer-password",
                ),
                "1000",
            )

    def test_deactivation_rejects_nonzero_balance_and_approves_zero_balance(self):
        request_id = account_service.submit_registration(
            "C4096",
            "customer03",
            "Third Customer",
            "customer-password",
        )
        request_service.verify_registration(self.field, request_id)
        account_id = request_service.approve_registration(
            self.accountant,
            request_id,
        )

        transaction_service.cashier_deposit(
            self.cashier,
            account_id,
            "1",
        )
        deactivation_id = account_service.submit_deactivation(
            account_id,
            "Close account",
        )
        approved, message = request_service.process_deactivation(
            self.accountant,
            deactivation_id,
        )
        self.assertFalse(approved)
        self.assertIn("Rejected", message)

        transaction_service.cashier_withdraw(
            self.cashier,
            account_id,
            "1",
        )
        second_request = account_service.submit_deactivation(
            account_id,
            "Close account after withdrawal",
        )
        approved, _ = request_service.process_deactivation(
            self.accountant,
            second_request,
        )
        self.assertTrue(approved)
        self.assertEqual(
            account_service.get_by_id(account_id)["status"],
            "deactivated",
        )

    def test_customer_transfer_is_atomic_and_creates_two_rows(self):
        first = account_service.submit_registration("C5001", "sender", "Sender", "password1")
        request_service.verify_registration(self.field, first)
        sender_id = request_service.approve_registration(self.accountant, first)
        second = account_service.submit_registration("C5002", "receiver", "Receiver", "password2")
        request_service.verify_registration(self.field, second)
        receiver_id = request_service.approve_registration(self.accountant, second)
        transaction_service.cashier_deposit(self.cashier, sender_id, "10")

        receipts = transaction_service.customer_transfer(
            account_service.authenticate_customer("sender", "password1"),
            receiver_id,
            "3.25",
        )
        self.assertEqual([r.amount_paise for r in receipts], [325, 325])
        self.assertEqual(account_service.get_by_id(sender_id)["balance_paise"], 675)
        self.assertEqual(account_service.get_by_id(receiver_id)["balance_paise"], 325)
        self.assertEqual(len([r for r in transaction_service.history(sender_id)
                              if r["type"] == "transfer"]), 1)
        with self.assertRaises(ValueError):
            transaction_service.customer_transfer(
                account_service.authenticate_customer("sender", "password1"),
                receiver_id,
                "100",
            )
        self.assertEqual(account_service.get_by_id(sender_id)["balance_paise"], 675)

    def test_customer_credential_changes_verify_current_and_refresh(self):
        request_id = account_service.submit_registration(
            "C6001", "credential-user", "Credential User", "password1")
        request_service.verify_registration(self.field, request_id)
        account_id = request_service.approve_registration(self.accountant, request_id)
        with self.assertRaises(ValueError):
            account_service.change_password(account_id, "wrong", "password2")
        updated = account_service.change_credentials(
            account_id, "password1", "renamed-user", "password2")
        self.assertEqual(updated["username"], "renamed-user")
        self.assertIsNotNone(account_service.authenticate_customer("renamed-user", "password2"))
        other_request = account_service.submit_registration(
            "C6002", "other-user", "Other User", "password1")
        request_service.verify_registration(self.field, other_request)
        other_id = request_service.approve_registration(self.accountant, other_request)
        with self.assertRaises(ValueError):
            account_service.change_username(other_id, "password1", "renamed-user")

    def test_portals_import_without_exposing_employee_dashboard(self):
        import customer_portal
        import employee_portal
        self.assertTrue(callable(customer_portal.main))
        self.assertTrue(callable(employee_portal.main))
        self.assertNotIn("dashboards", customer_portal.__dict__)


if __name__ == "__main__":
    unittest.main()
