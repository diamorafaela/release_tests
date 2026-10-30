"""Exercise Diamo account boundaries with temporary, non-admin identities."""

import base64
import json
import secrets
from contextlib import contextmanager

from ..client import FrappeAPIError, FrappeClient
from .base import CheckFailed, ReleaseSuite, Step


class DiamoBaseAccessSuite(ReleaseSuite):
    name = "diamo_base_access"
    required_app = "diamoerp_base"
    description = (
        "Dedicated API authentication, credential revocation, and reduced project user permissions."
    )
    independent_steps = True

    def build_steps(self, versions):
        return [
            Step(
                "API token and Basic identity; block interactive login; revoke keys",
                self.api_lifecycle,
            ),
            Step(
                "reduced user can use tasks and links but cannot access invoices", self.reduced_user
            ),
        ]

    def api_lifecycle(self, client, ctx):
        with temporary_user(client, api=True) as (name, password):
            keys = client.call("frappe.core.doctype.user.user.generate_keys", user=name)
            with isolated_client(client) as api:
                api.use_token(keys["api_key"], keys["api_secret"])
                assert_identity(api, name)
                encoded = base64.b64encode(
                    f"{keys['api_key']}:{keys['api_secret']}".encode()
                ).decode()
                api.session.headers["Authorization"] = f"Basic {encoded}"
                assert_identity(api, name)
                page = api.get_page("app", allow_redirects=False)
                if page.status_code != 401:
                    raise AssertionError(
                        f"API credentials outside /api/ must return 401, got {page.status_code}"
                    )
                with isolated_client(client) as interactive:
                    expect_rejection(
                        lambda: interactive.login(name, password), 401, "AuthenticationError"
                    )
                save_fields(client, name, enable_api_access=0)
                stored = client.get_doc("User", name)
                if stored.get("api_key") or stored.get("api_secret"):
                    raise AssertionError("converting to an ERP user must clear API credentials")
                expect_rejection(lambda: assert_identity(api, name), 401, "AuthenticationError")
                api.use_token(keys["api_key"], keys["api_secret"])
                expect_rejection(lambda: assert_identity(api, name), 401, "AuthenticationError")
                with isolated_client(client) as interactive:
                    interactive.login(name, password)
                    assert_identity(interactive, name)
                expect_rejection(
                    lambda: client.call("frappe.core.doctype.user.user.generate_keys", user=name),
                    403,
                    "PermissionError",
                )

    def reduced_user(self, client, ctx):
        with (
            temporary_user(client, reduced=True) as (name, password),
            isolated_client(client) as reduced,
        ):
            reduced.login(name, password)
            assert_identity(reduced, name)
            customer = reduced.get_doc("Customer", "Release Test Customer")
            if customer.get("name") != "Release Test Customer":
                raise AssertionError("reduced user must be able to read the linked customer")
            task = reduced.insert({"doctype": "Task", "subject": f"Release test {name}"})
            try:
                if reduced.get_doc("Task", task["name"])["subject"] != task["subject"]:
                    raise AssertionError("reduced user cannot read the task it created")
                expect_rejection(
                    lambda: reduced.get_list("Purchase Invoice"), 403, "PermissionError"
                )
                expect_rejection(
                    lambda: reduced.insert(
                        {"doctype": "Sales Invoice", "customer": customer["name"]}
                    ),
                    403,
                    "PermissionError",
                )
                self.reject_invoice_access(client, reduced, customer["name"])
            finally:
                reduced.call(
                    "frappe.client.set_value",
                    doctype="Task",
                    name=task["name"],
                    fieldname="status",
                    value="Cancelled",
                )

    def reject_invoice_access(self, client, reduced, customer):
        invoice = client.insert(
            {
                "doctype": "Sales Invoice",
                "company": "Diamo Release Test",
                "customer": customer,
                "items": [{"item_code": "RT-ITEM", "qty": 1, "rate": 100}],
            }
        )
        try:
            expect_rejection(
                lambda: reduced.get_doc("Sales Invoice", invoice["name"]), 403, "PermissionError"
            )
            links = reduced.get_list(
                "Sales Invoice",
                filters={"name": invoice["name"]},
                fields=["name", "grand_total", "outstanding_amount"],
            )
            exposed = sorted({key for row in links for key in row if key != "name"})
            if exposed:
                raise CheckFailed(
                    "reduced user invoice search must not expose financial amounts",
                    expected="no grand_total or outstanding_amount in the response",
                    actual=f"exposed fields: {exposed}",
                    user=reduced.logged_in_user,
                    roles=["Usuario Reducido de Proyecto"],
                    endpoint="/api/resource/Sales Invoice",
                    hint="Review the reduced user field permissions and invoice list API.",
                )
        finally:
            client.delete("Sales Invoice", invoice["name"])


@contextmanager
def temporary_user(client, *, api=False, reduced=False):
    name = f"release-test-{secrets.token_hex(8)}@example.com"
    password = secrets.token_urlsafe(32) + "aA1!"
    doc = {
        "doctype": "User",
        "email": name,
        "first_name": "Release Test",
        "enabled": 1,
        "send_welcome_email": 0,
        "new_password": password,
        "user_type": "Usuario Reducido de Proyecto" if reduced else "System User",
        "enable_api_access": int(api),
    }
    if not reduced:
        doc["roles"] = [{"role": "Accounts User"}]
    client.insert(doc)
    try:
        yield name, password
    finally:
        # Keep the audit identity, release its license and revoke its credentials.
        save_fields(client, name, enabled=0)


@contextmanager
def isolated_client(parent):
    client = FrappeClient(
        parent.url, host_header=parent.session.headers.get("Host"), timeout=parent.timeout
    )
    try:
        yield client
    finally:
        client.session.close()


def save_fields(client, user, **fields):
    doc = client.get_doc("User", user)
    doc.update(fields)
    client.call("frappe.client.save", doc=json.dumps(doc))


def assert_identity(client, expected):
    if client.call("frappe.auth.get_logged_user") != expected:
        raise AssertionError("authenticated identity does not match the test user")


def expect_rejection(action, status, exc_type):
    try:
        action()
    except FrappeAPIError as error:
        if error.status != status or error.exc_type != exc_type:
            raise
    else:
        raise CheckFailed(
            "restricted operation must be rejected",
            expected=f"{status} {exc_type}",
            actual="operation succeeded",
        )
