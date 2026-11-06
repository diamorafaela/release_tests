"""ERPNext buying cycle: Purchase Order -> Purchase Receipt -> Purchase Invoice -> Payment."""

from __future__ import annotations

from datetime import date, timedelta

from .. import factories
from ..client import FrappeClient
from ..gating import Versions
from .base import ReleaseSuite, Step


def _masters(client: FrappeClient, ctx: dict) -> None:
    ctx["company"] = factories.ensure_company(client)
    ctx["supplier"] = factories.ensure_supplier(client)
    ctx["warehouse"] = factories.ensure_warehouse(client, ctx["company"])
    ctx["item"] = factories.ensure_stock_item(client, ctx["company"], ctx["warehouse"])


def _purchase_order(client: FrappeClient, ctx: dict) -> None:
    schedule = str(date.today() + timedelta(days=7))
    doc = {
        "doctype": "Purchase Order",
        "supplier": ctx["supplier"],
        "company": ctx["company"],
        "schedule_date": schedule,
        "items": [
            {
                "item_code": ctx["item"],
                "qty": 5,
                "rate": 50,
                "warehouse": ctx["warehouse"],
                "schedule_date": schedule,
            }
        ],
    }
    ctx["po"] = client.submit({**client.insert(doc)})["name"]


def _purchase_receipt(client: FrappeClient, ctx: dict) -> None:
    pr = client.call(
        "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt",
        source_name=ctx["po"],
    )
    pr["doctype"] = "Purchase Receipt"
    ctx["pr"] = client.submit({**client.insert(pr)})["name"]


def _purchase_invoice(client: FrappeClient, ctx: dict) -> None:
    pi = client.call(
        "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice",
        source_name=ctx["pr"],
    )
    pi["doctype"] = "Purchase Invoice"
    # A non-fiscal Diamo purchase leaves all four fiscal identifiers empty.
    # Setting only bill_no activates fiscal validation and is an invalid document.
    if "diamoerp_argentina" not in client.get_versions():
        pi["bill_no"] = f"SMK-{ctx['po']}"
    ctx["pi"] = client.submit({**client.insert(pi)})["name"]


def _payment(client: FrappeClient, ctx: dict) -> None:
    from .payment_flow import settle_invoice

    settle_invoice(client, "Purchase Invoice", ctx["pi"])


def _verify_settled(client: FrappeClient, ctx: dict) -> None:
    pi = client.get_doc("Purchase Invoice", ctx["pi"])
    outstanding = float(pi.get("outstanding_amount") or 0)
    if abs(outstanding) > 0.01:
        raise AssertionError(f"purchase invoice still outstanding: {outstanding}")


class ERPNextBuyingSuite(ReleaseSuite):
    name = "erpnext_buying"
    required_app = "erpnext"
    description = "Full buying cycle: Purchase Order -> Purchase Receipt -> Purchase Invoice -> Payment, invoice settled."

    def build_steps(self, versions: Versions) -> list[Step]:
        return [
            Step("ensure masters", _masters),
            Step("submit Purchase Order", _purchase_order),
            Step("make + submit Purchase Receipt", _purchase_receipt),
            Step("make + submit Purchase Invoice", _purchase_invoice),
            Step("submit Payment Entry", _payment),
            Step("verify invoice settled", _verify_settled),
        ]
