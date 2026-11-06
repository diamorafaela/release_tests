"""ERPNext service item: a non-stock item billed straight on a Sales Invoice."""

from __future__ import annotations

from .. import factories
from ..client import FrappeClient
from ..gating import Versions
from .base import ReleaseSuite, Step


def _masters(client: FrappeClient, ctx: dict) -> None:
    ctx["company"] = factories.ensure_company(client)
    ctx["customer"] = factories.ensure_customer(client)
    ctx["item"] = factories.ensure_service_item(client)


def _sales_invoice(client: FrappeClient, ctx: dict) -> None:
    doc = {
        "doctype": "Sales Invoice",
        "company": ctx["company"],
        "customer": ctx["customer"],
        "update_stock": 0,
        "items": [{"item_code": ctx["item"], "qty": 1, "rate": 500}],
    }
    ctx["invoice"] = client.submit({**client.insert(doc)})["name"]


def _payment(client: FrappeClient, ctx: dict) -> None:
    from .payment_flow import settle_invoice

    settle_invoice(client, "Sales Invoice", ctx["invoice"])


def _verify_settled(client: FrappeClient, ctx: dict) -> None:
    invoice = client.get_doc("Sales Invoice", ctx["invoice"])
    outstanding = float(invoice.get("outstanding_amount") or 0)
    if abs(outstanding) > 0.01:
        raise AssertionError(f"service invoice still outstanding: {outstanding}")


class ERPNextServiceSuite(ReleaseSuite):
    name = "erpnext_service"
    required_app = "erpnext"
    description = "Service item (non-stock): billed directly on a Sales Invoice, then settled by Payment."

    def build_steps(self, versions: Versions) -> list[Step]:
        return [
            Step("ensure masters (service item)", _masters),
            Step("submit Sales Invoice", _sales_invoice),
            Step("submit Payment Entry", _payment),
            Step("verify invoice settled", _verify_settled),
        ]
