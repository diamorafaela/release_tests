"""Guard the Diamo ERPNext fork's amount-based service returns."""

from ..client import FrappeAPIError
from . import diamo_accounting as checks
from .base import ReleaseSuite, Step


class DiamoServiceCreditsSuite(ReleaseSuite):
    name = "diamo_service_credits"
    required_app = "diamoerp_base"
    description = "Service credits of 40 + 60 after returning all units; reject excess credit. Requires Diamo ERPNext fork."

    def build_steps(self, versions):
        return [
            Step("verify isolated ARS fixtures", checks.prepare),
            Step("submit service invoice for 100", checks.invoice),
            Step("credit all units for only 40", self.first_credit),
            Step("credit remaining 60 despite returned quantity", self.remaining_credit),
            Step("reject credit exceeding original amount", self.reject_excess),
        ]

    def first_credit(self, client, ctx):
        draft = self.make_return(client, ctx)
        draft["items"][0].update({"qty": -1, "rate": 40, "price_list_rate": 40})
        credit = client.submit(client.insert(draft))
        checks.amount(credit.get("grand_total"), -40, "first credit")
        ctx["first_credit"] = credit["name"]

    def remaining_credit(self, client, ctx):
        draft = self.make_return(client, ctx)
        if len(draft.get("items", [])) != 1:
            raise AssertionError("remaining service amount must still be returnable")
        checks.amount(draft["items"][0].get("qty"), -1, "remaining service quantity")
        checks.amount(draft["items"][0].get("rate"), 60, "remaining service value")
        credit = client.submit(client.insert(draft))
        checks.amount(credit.get("grand_total"), -60, "second credit")

    def reject_excess(self, client, ctx):
        invoice = ctx["invoice"]
        draft = {
            "doctype": "Sales Invoice",
            "company": ctx["company"],
            "customer": ctx["customer"],
            "is_return": 1,
            "return_against": invoice["name"],
            "currency": "ARS",
            "items": [
                {
                    "item_code": ctx["item"],
                    "qty": -1,
                    "rate": 1,
                    "sales_invoice_item": invoice["items"][0]["name"],
                }
            ],
        }
        try:
            client.submit(client.insert(draft))
        except FrappeAPIError as error:
            if error.status != 417 or error.exc_type != "StockOverReturnError":
                raise
        else:
            raise AssertionError("excess service credit was accepted")

    def make_return(self, client, ctx):
        return client.call(
            "erpnext.accounts.doctype.sales_invoice.sales_invoice.make_sales_return",
            source_name=ctx["invoice"]["name"],
        )
