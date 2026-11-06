"""Merged app fields and Base's administrative boundaries after framework upgrades."""

import secrets

from ..client import FrappeAPIError
from ..diamo_contracts import FIELDS
from .base import CheckFailed, ReleaseSuite, Step


class DiamoCustomizationsSuite(ReleaseSuite):
    name = "diamo_customizations"
    required_app = "diamoerp_base"
    description = "Shipped Diamo fields survive meta loading; non-Administrator cannot create administrative customizations."

    def applies(self, versions):
        return all(app in versions for app in ("frappe", "erpnext", "diamoerp_base", "diamoerp_argentina"))

    def build_steps(self, versions):
        return [
            Step("verify shipped Diamo field contracts", self.fields),
            Step("verify QA administrative boundaries", self.administrative_boundaries),
        ]

    def fields(self, client, ctx):
        for doctype, expected in FIELDS.items():
            rows = client.call("diamoerp_base.api.get_doctype_fields", doctype=doctype)
            actual = {row["fieldname"]: (row["fieldtype"], row.get("options") or None) for row in rows}
            for field, contract in expected.items():
                if actual.get(field) != contract:
                    raise CheckFailed(f"merged field {doctype}.{field}", expected=str(contract), actual=str(actual.get(field)))

    def administrative_boundaries(self, client, ctx):
        user = client.call("frappe.auth.get_logged_user")
        if user in ("Administrator", "Guest"):
            raise CheckFailed("operational QA identity", expected="authenticated non-Administrator", actual=user)
        suffix = secrets.token_hex(8)
        documents = [
            {"doctype": "Custom Field", "dt": "ToDo", "fieldname": f"rt_boundary_{suffix}",
             "label": "Release boundary probe", "fieldtype": "Data"},
            {"doctype": "Client Script", "name": f"RT Boundary {suffix}", "dt": "ToDo",
             "view": "Form", "enabled": 0, "script": "// Disabled release boundary probe"},
            {"doctype": "Server Script", "name": f"RT Boundary {suffix}", "script_type": "API",
             "api_method": f"rt_boundary_{suffix}", "disabled": 1, "script": "frappe.response['message'] = None"},
        ]
        for document in documents:
            try:
                created = client.insert(document)
            except FrappeAPIError as error:
                if error.status != 403 or error.exc_type != "PermissionError":
                    raise
            else:
                client.delete(document["doctype"], created["name"])
                raise CheckFailed(f"Base protects {document['doctype']}", expected="403 PermissionError",
                                  actual="creation succeeded", user=user)
