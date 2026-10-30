"""Framework release suite: login, identity, and a full CRUD round-trip.

Runs on every Frappe site (no specific app required). Proves that auth works,
the REST layer is up, and documents can be created, read, and deleted.
"""

from __future__ import annotations

from ..client import FrappeClient
from ..gating import Versions
from .base import ReleaseSuite, Step

_TODO_DESC = "release_tests CRUD round-trip"


def _whoami(client: FrappeClient, ctx: dict) -> None:
    user = client.call("frappe.auth.get_logged_user")
    if not user or user == "Guest":
        raise AssertionError(f"expected an authenticated user, got {user!r}")
    ctx["user"] = user


def _create_todo(client: FrappeClient, ctx: dict) -> None:
    doc = client.insert({"doctype": "ToDo", "description": _TODO_DESC, "allocated_to": ctx["user"]})
    if not doc.get("name"):
        raise AssertionError("ToDo insert returned no name")
    ctx["todo"] = doc["name"]


def _read_todo(client: FrappeClient, ctx: dict) -> None:
    doc = client.get_doc("ToDo", ctx["todo"])
    if doc.get("description") != _TODO_DESC:
        raise AssertionError("ToDo read back with unexpected description")


def _delete_todo(client: FrappeClient, ctx: dict) -> None:
    client.call("frappe.client.delete", doctype="ToDo", name=ctx["todo"])


class CoreFrappeSuite(ReleaseSuite):
    name = "core_frappe"
    required_app = "frappe"
    description = "Framework basics: authenticated login, whoami, and a ToDo create/read/delete round-trip."

    def build_steps(self, versions: Versions) -> list[Step]:
        return [
            Step("authenticated whoami", _whoami),
            Step("create ToDo", _create_todo),
            Step("read ToDo", _read_todo),
            Step("delete ToDo", _delete_todo),
        ]
