"""Run release credential checks through real authentication and RPC controllers."""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.auth import validate_auth_via_api_keys
from frappe.tests import IntegrationTestCase

from release_tests.client import FrappeAPIError
from release_tests.suites.diamo_base_access import DiamoBaseAccessSuite

from . import QA_USER
from .identity import ensure_executor
from .test_fork_flows import LocalAPIClient


class AuthenticatedLocalClient(LocalAPIClient):
    def __init__(self):
        self.session = frappe._dict(headers={})

    def use_token(self, key, secret):
        self.session.headers["Authorization"] = f"token {key}:{secret}"

    def call(self, method, **kwargs):
        previous = frappe.session.user
        try:
            frappe.set_user("Guest")
            with (
                patch.object(frappe.local, "login_manager", frappe._dict(user="Guest"), create=True),
                patch("frappe.get_request_header", return_value=None),
            ):
                validate_auth_via_api_keys(self.session.headers["Authorization"].split(" ", 1))
            return super().call(method, **kwargs)
        except frappe.AuthenticationError as error:
            raise FrappeAPIError("Authentication rejected", status=401, exc_type="AuthenticationError") from error
        finally:
            frappe.set_user(previous)


@contextmanager
def authenticated_client(parent):
    yield AuthenticatedLocalClient()


class TestAPICredentials(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.enterContext(patch("frappe.db.commit"))
        self.enterContext(patch("diamoerp_base.overrides.user.get_limits",
                                return_value=frappe._dict(users=1000, api_users=100)))
        self.assertEqual(ensure_executor(), [])
        frappe.set_user(QA_USER)
        self.enterContext(patch("release_tests.suites.diamo_base_access.isolated_client", authenticated_client))

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_rotation_revokes_both_authentication_schemes(self):
        DiamoBaseAccessSuite().rotate_credentials(LocalAPIClient(), {})

    def test_reenable_does_not_restore_old_credentials(self):
        DiamoBaseAccessSuite().disable_api_user(LocalAPIClient(), {})
