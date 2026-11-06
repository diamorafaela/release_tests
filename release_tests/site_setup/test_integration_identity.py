"""Managed identity contracts run locally with all writes rolled back."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from . import QA_USER
from .identity import ensure_executor


class TestIntegrationIdentity(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        from diamoerp_base.integration_user import provision

        frappe.set_user("Administrator")
        self.enterContext(patch("frappe.db.commit"))
        with patch("diamoerp_base.overrides.user.get_limits", return_value=frappe._dict(users=1000, api_users=100)):
            self.assertEqual(ensure_executor(), [])
        self.managed = provision()

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_provision_is_repeatable_and_preserves_credentials(self):
        from diamoerp_base.integration_user import provision
        from diamoerp_base.overrides.user import generate_keys

        keys = generate_keys(self.managed)
        self.assertEqual(provision(), self.managed)
        self.assertEqual(provision(), self.managed)
        user = frappe.get_doc("User", self.managed)
        self.assertEqual(user.api_key, keys["api_key"])
        self.assertEqual(user.get_password("api_secret"), keys["api_secret"])

    def test_system_manager_cannot_read_manage_or_rotate_managed_identity(self):
        from diamoerp_base.integration_user import provision
        from diamoerp_base.overrides.user import generate_keys
        from release_tests.suites.diamo_base_access import DiamoBaseAccessSuite

        from .test_fork_flows import LocalAPIClient

        user = frappe.get_doc("User", self.managed)
        frappe.set_user(QA_USER)
        self.assertIn("System Manager", frappe.get_roles())
        self.assertFalse(frappe.has_permission("User", "read", doc=user))
        self.assertEqual(frappe.get_list("User", filters={"name": self.managed}), [])
        DiamoBaseAccessSuite().managed_identity_visibility(LocalAPIClient(), {})
        for action in (provision, lambda: generate_keys(self.managed), user.save):
            with self.assertRaises(frappe.PermissionError):
                action()

    def test_managed_user_is_excluded_from_license_allocations(self):
        from diamoerp_base.overrides.user import get_enabled_users_for_update

        user = frappe.get_doc("User", self.managed)
        user.enabled = 1
        with patch("diamoerp_base.overrides.user.get_limits", return_value=frappe._dict(users=1, api_users=0)):
            user.save()
        self.assertTrue(user.enable_api_access)
        for api_user in (True, False):
            self.assertNotIn(self.managed, get_enabled_users_for_update(api_user=api_user))

    def test_administrator_cannot_remove_api_classification_or_required_role(self):
        for field, value in (("enable_api_access", 0), ("custom_diamo_integration", 0)):
            user = frappe.get_doc("User", self.managed)
            user.set(field, value)
            with self.assertRaises(frappe.ValidationError):
                user.save()
        user = frappe.get_doc("User", self.managed)
        user.set("roles", [row for row in user.roles if row.role != "System Manager"])
        with self.assertRaises(frappe.ValidationError):
            user.save()

    def test_managed_identity_cannot_be_deleted_or_renamed(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc("User", self.managed)
        with self.assertRaises(frappe.ValidationError):
            frappe.rename_doc("User", self.managed, "release-managed-probe@example.com")
