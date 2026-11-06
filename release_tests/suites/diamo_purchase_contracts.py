"""Argentina purchase hooks: fiscal completeness and cross-currency order mapping."""

from datetime import date

from .. import factories
from ..client import FrappeAPIError
from .base import CheckFailed, ReleaseSuite, Step
from .diamo_accounting import amount


class DiamoPurchaseContractsSuite(ReleaseSuite):
    name = "diamo_purchase_contracts"
    required_app = "diamoerp_argentina"
    description = "Reject incomplete fiscal purchase identifiers; invoice an ARS purchase order in USD through the Argentina override."

    def build_steps(self, versions):
        return [
            Step("prepare isolated purchase contract fixtures", self.prepare),
            Step("reject incomplete fiscal purchase identifiers", self.incomplete_fiscal),
            Step("invoice ARS purchase order in USD", self.cross_currency),
        ]

    def prepare(self, client, ctx):
        ctx["company"] = factories.ensure_company(client)
        company = client.get_doc("Company", ctx["company"])
        if company["country"] != "Argentina" or company["default_currency"] != "ARS":
            raise CheckFailed("Argentina purchase fixtures", expected="Argentina / ARS", actual=str(company["name"]))
        ctx["supplier"] = factories.ensure_supplier(client)
        ctx["item"] = factories.ensure_item(client)

    def incomplete_fiscal(self, client, ctx):
        draft = client.insert({
            "doctype": "Purchase Invoice", "company": ctx["company"], "supplier": ctx["supplier"],
            "currency": "ARS", "items": [{"item_code": ctx["item"], "qty": 1, "rate": 100}],
        })
        draft["bill_no"] = "RT-INCOMPLETE"
        try:
            try:
                result = client.submit(draft)
            except FrappeAPIError as error:
                if error.status != 417 or error.exc_type != "ValidationError" or "Tipo de Comprobante" not in str(error):
                    raise
            else:
                client.cancel("Purchase Invoice", result["name"])
                raise CheckFailed("incomplete fiscal identifiers rejected", expected="fiscal completeness validation",
                                  actual="invoice submitted")
        finally:
            client.delete("Purchase Invoice", draft["name"])

    def cross_currency(self, client, ctx):
        order = client.submit(client.insert({
            "doctype": "Purchase Order", "company": ctx["company"], "supplier": ctx["supplier"],
            "currency": "ARS", "schedule_date": str(date.today()),
            "items": [{"item_code": ctx["item"], "qty": 2, "rate": 100, "schedule_date": str(date.today())}],
        }))
        invoice = client.call("erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice",
                              source_name=order["name"])
        invoice.update(currency="USD", conversion_rate=100, ignore_pricing_rule=1)
        # Keep nominal rates: Buying Settings may require the same rate as the PO.
        # The contract here is a different invoice currency, not a rate-policy bypass.
        for row in invoice["items"]:
            row.update(rate=100, price_list_rate=100)
        submitted = client.submit(client.insert(invoice))
        amount(submitted.get("grand_total"), 200, "USD purchase total")
        amount(submitted.get("base_grand_total"), 20000, "ARS purchase total")
        if not all(row.get("purchase_order") == order["name"] for row in submitted["items"]):
            raise CheckFailed("cross-currency invoice retains order links", expected=order["name"], actual="missing order link")
        client.cancel("Purchase Invoice", submitted["name"])
        client.cancel("Purchase Order", order["name"])
