"""ERPNext release suite (v1 depth: masters + one invoice + one payment).

Flow: ensure Company / Customer / Item masters exist, then submit a single
Sales Invoice and settle it with a Payment Entry. v2 will extend this into the
full Quotation -> Sales Order -> Delivery Note -> Sales Invoice -> Payment ->
reconciliation chain.
"""

from __future__ import annotations

from .. import factories
from ..client import FrappeClient
from ..gating import Versions
from .base import ReleaseSuite, Step


def _masters(client: FrappeClient, ctx: dict) -> None:
    ctx["company"] = factories.ensure_company(client)
    ctx["customer"] = factories.ensure_customer(client)
    ctx["item"] = factories.ensure_item(client)


def _sales_invoice(client: FrappeClient, ctx: dict) -> None:
    invoice = {
        "doctype": "Sales Invoice",
        "company": ctx["company"],
        "customer": ctx["customer"],
        "update_stock": 0,
        "items": [{"item_code": ctx["item"], "qty": 1, "rate": 100}],
    }
    draft = client.insert(invoice)
    submitted = client.submit({**draft})
    if submitted.get("docstatus") != 1:
        raise AssertionError(f"Sales Invoice not submitted (docstatus={submitted.get('docstatus')})")
    ctx["invoice"] = submitted["name"]
    ctx["grand_total"] = submitted.get("grand_total") or submitted.get("rounded_total") or 100


def _payment_entry(client: FrappeClient, ctx: dict) -> None:
    from .payment_flow import settle_invoice

    submitted = settle_invoice(client, "Sales Invoice", ctx["invoice"])
    ctx["payment"] = submitted["name"]


def _verify_outstanding(client: FrappeClient, ctx: dict) -> None:
    doc = client.get_doc("Sales Invoice", ctx["invoice"])
    outstanding = float(doc.get("outstanding_amount") or 0)
    if abs(outstanding) > 0.01:
        raise AssertionError(f"invoice still outstanding after payment: {outstanding}")


class ERPNextSuite(ReleaseSuite):
    name = "erpnext"
    required_app = "erpnext"
    description = "Sales flow: ensure Company/Customer/Item, submit a Sales Invoice and a Payment Entry, verify the invoice is settled."

    def build_steps(self, versions: Versions) -> list[Step]:
        return [
            Step("ensure masters (company/customer/item)", _masters),
            Step("submit Sales Invoice", _sales_invoice),
            Step("submit Payment Entry", _payment_entry),
            Step("verify invoice settled", _verify_outstanding),
        ]
