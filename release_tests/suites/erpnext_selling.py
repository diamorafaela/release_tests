"""ERPNext full selling cycle: Quotation -> SO -> Delivery Note -> SI -> Payment.

Uses the same whitelisted mapper methods the ERPNext UI's "Create > X" buttons
call, so each document is built from the previous one. Kept deliberately simple:
one stock item, small quantities.
"""

from __future__ import annotations

from datetime import date, timedelta

from .. import factories
from ..client import FrappeClient
from ..gating import Versions
from .base import ReleaseSuite, Step


def _masters(client: FrappeClient, ctx: dict) -> None:
    ctx["company"] = factories.ensure_company(client)
    ctx["customer"] = factories.ensure_customer(client)
    ctx["warehouse"] = factories.ensure_warehouse(client, ctx["company"])
    ctx["item"] = factories.ensure_stock_item(client, ctx["company"], ctx["warehouse"])
    # Give the item stock so a Delivery Note can ship it.
    factories.ensure_stock_on_hand(client, ctx["company"], ctx["item"], ctx["warehouse"], qty=10)


def _quotation(client: FrappeClient, ctx: dict) -> None:
    doc = {
        "doctype": "Quotation",
        "quotation_to": "Customer",
        "party_name": ctx["customer"],
        "company": ctx["company"],
        "items": [{"item_code": ctx["item"], "qty": 2, "rate": 100, "warehouse": ctx["warehouse"]}],
    }
    ctx["quotation"] = client.submit({**client.insert(doc)})["name"]


def _sales_order(client: FrappeClient, ctx: dict) -> None:
    so = client.call(
        "erpnext.selling.doctype.quotation.quotation.make_sales_order", source_name=ctx["quotation"]
    )
    so["doctype"] = "Sales Order"
    delivery = str(date.today() + timedelta(days=7))
    so["delivery_date"] = delivery  # mandatory on v16
    for item in so.get("items", []):
        item.setdefault("delivery_date", delivery)
    ctx["sales_order"] = client.submit({**client.insert(so)})["name"]


def _delivery_note(client: FrappeClient, ctx: dict) -> None:
    dn = client.call(
        "erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
        source_name=ctx["sales_order"],
    )
    dn["doctype"] = "Delivery Note"
    ctx["delivery_note"] = client.submit({**client.insert(dn)})["name"]


def _sales_invoice(client: FrappeClient, ctx: dict) -> None:
    si = client.call(
        "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice",
        source_name=ctx["delivery_note"],
    )
    si["doctype"] = "Sales Invoice"
    ctx["invoice"] = client.submit({**client.insert(si)})["name"]


def _payment(client: FrappeClient, ctx: dict) -> None:
    from .payment_flow import settle_invoice

    settle_invoice(client, "Sales Invoice", ctx["invoice"])


def _verify_settled(client: FrappeClient, ctx: dict) -> None:
    invoice = client.get_doc("Sales Invoice", ctx["invoice"])
    outstanding = float(invoice.get("outstanding_amount") or 0)
    if abs(outstanding) > 0.01:
        raise AssertionError(f"invoice still outstanding after payment: {outstanding}")


class ERPNextSellingSuite(ReleaseSuite):
    name = "erpnext_selling"
    required_app = "erpnext"
    description = "Full sales cycle: Quotation -> Sales Order -> Delivery Note -> Sales Invoice -> Payment, invoice settled."

    def build_steps(self, versions: Versions) -> list[Step]:
        return [
            Step("ensure masters + stock", _masters),
            Step("submit Quotation", _quotation),
            Step("make + submit Sales Order", _sales_order),
            Step("make + submit Delivery Note", _delivery_note),
            Step("make + submit Sales Invoice", _sales_invoice),
            Step("submit Payment Entry", _payment),
            Step("verify invoice settled", _verify_settled),
        ]
