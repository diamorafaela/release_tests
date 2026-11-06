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
        "API authentication, secret rotation, disable/re-enable revocation, and reduced user invoice boundaries."
    )
    independent_steps = True

    def build_steps(self, versions):
        return [
            Step("rotate API secret and reject previous credentials", self.rotate_credentials),
            Step("disable API user and reject token and Basic credentials", self.disable_api_user),
            Step("reduced user cannot read financial values or mutate invoices through RPC", self.reduced_invoice_rpc),
            Step("QA cannot read or list the managed Diamo integration identity", self.managed_identity_visibility),
            Step(
                "API token and Basic identity; block interactive login; revoke keys",
                self.api_lifecycle,
            ),
            Step(
                "reduced user can use tasks and links but cannot access invoices", self.reduced_user
            ),
        ]

    def rotate_credentials(self, client, ctx):
        with temporary_user(client, api=True) as (name, _):
            old = client.call("frappe.core.doctype.user.user.generate_keys", user=name)
            with isolated_client(client) as api:
                api.use_token(old["api_key"], old["api_secret"])
                assert_identity(api, name)
                new = client.call("frappe.core.doctype.user.user.generate_keys", user=name)
                if old["api_secret"] == new["api_secret"]:
                    raise AssertionError("rotation must replace the API secret")
                reject_credentials(api, old)
                api.use_token(new["api_key"], new["api_secret"])
                assert_identity(api, name)
                expect_rejection(
                    lambda: api.call("frappe.core.doctype.user.user.generate_keys", user=name),
                    403, "PermissionError",
                )
                assert_identity(api, name)

    def managed_identity_visibility(self, client, ctx):
        name = "integracion@diamo.com.ar"
        expect_rejection(lambda: client.get_doc("User", name), 403, "PermissionError")
        rows = client.get_list("User", filters={"name": name}, fields=["name"])
        if rows:
            raise CheckFailed("managed identity hidden from QA lists", expected="no rows", actual="identity exposed")

    def disable_api_user(self, client, ctx):
        with temporary_user(client, api=True) as (name, _):
            keys = client.call("frappe.core.doctype.user.user.generate_keys", user=name)
            with isolated_client(client) as api:
                api.use_token(keys["api_key"], keys["api_secret"])
                assert_identity(api, name)
                save_fields(client, name, enabled=0)
                reject_credentials(api, keys)
                stored = client.get_doc("User", name)
                if stored.get("api_key") or stored.get("api_secret"):
                    raise AssertionError("disabled API user must have no credentials")
                save_fields(client, name, enabled=1)
                reject_credentials(api, keys)
                fresh = client.call("frappe.core.doctype.user.user.generate_keys", user=name)
                api.use_token(fresh["api_key"], fresh["api_secret"])
                assert_identity(api, name)

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

    def reduced_invoice_rpc(self, client, ctx):
        with temporary_user(client, reduced=True) as (name, password), isolated_client(client) as reduced:
            reduced.login(name, password)
            invoice = client.insert({
                "doctype": "Sales Invoice", "company": "Diamo Release Test",
                "customer": "Release Test Customer",
                "items": [{"item_code": "RT-ITEM", "qty": 1, "rate": 100}],
            })
            try:
                reject_invoice_mutations(reduced, invoice)
                for field in ("grand_total", "base_grand_total", "outstanding_amount"):
                    expect_rejection(lambda: reduced.call(
                        "frappe.client.get_value", doctype="Sales Invoice",
                        filters={"name": invoice["name"]}, fieldname=field,
                    ), 403, "PermissionError")
                stored = client.get_doc("Sales Invoice", invoice["name"])
                if stored.get("remarks") != invoice.get("remarks"):
                    raise AssertionError("denied RPC changed invoice remarks")
            finally:
                client.delete("Sales Invoice", invoice["name"])

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
                fields=["name"],
            )
            if links != [{"name": invoice["name"]}]:
                raise CheckFailed("reduced user can select the invoice link without extra fields",
                                  expected=str([{"name": invoice["name"]}]), actual=str(links))
            try:
                links = reduced.get_list(
                    "Sales Invoice", filters={"name": invoice["name"]},
                    fields=["name", "grand_total", "base_grand_total", "outstanding_amount"],
                )
            except FrappeAPIError as error:
                if error.status == 403 and error.exc_type == "PermissionError":
                    return
                raise
            exposed = sorted({key for row in links for key in row if key != "name"})
            if exposed:
                raise CheckFailed(
                    "reduced user invoice search must not expose financial amounts",
                    expected="no grand_total, base_grand_total or outstanding_amount in the response",
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


def reject_invoice_mutations(client, invoice):
    expect_rejection(lambda: client.call(
        "frappe.client.set_value", doctype="Sales Invoice", name=invoice["name"],
        fieldname="remarks", value="Unauthorized release probe",
    ), 403, "PermissionError")
    expect_rejection(lambda: client.call(
        "frappe.client.save", doc=json.dumps({**invoice, "remarks": "Unauthorized release probe"}),
    ), 403, "PermissionError")
    expect_rejection(lambda: client.delete("Sales Invoice", invoice["name"]), 403, "PermissionError")


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


def reject_credentials(client, keys):
    client.use_token(keys["api_key"], keys["api_secret"])
    expect_rejection(lambda: client.call("frappe.auth.get_logged_user"), 401, "AuthenticationError")
    encoded = base64.b64encode(f"{keys['api_key']}:{keys['api_secret']}".encode()).decode()
    client.session.headers["Authorization"] = f"Basic {encoded}"
    expect_rejection(lambda: client.call("frappe.auth.get_logged_user"), 401, "AuthenticationError")


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
