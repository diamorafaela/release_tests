"""One receipt with separate cash and bank movements."""

from . import diamo_accounting as checks
from .base import Step
from .diamo_argentina_payments import DiamoArgentinaPaymentsSuite


class DiamoCombinedReceiptsSuite(DiamoArgentinaPaymentsSuite):
    name = "diamo_combined_receipts"
    description = "ARS 100 receipt split into bank 60.01 and cash 39.99, ledger and cancellation."

    def build_steps(self, versions):
        return [
            Step("verify isolated ARS fixtures", checks.prepare),
            Step("submit invoice for ARS 100", checks.invoice),
            Step("receive bank 60.01 and cash 39.99", self.receive),
            Step("verify separate cash, bank and receivable movements", self.verify),
            Step("cancel combined receipt and restore debt", self.cancel),
        ]

    def receive(self, client, ctx):
        payment = client.call(
            "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
            dt="Sales Invoice", dn=ctx["invoice"]["name"],
        )
        methods = []
        ctx["movements"] = {payment["paid_from"]: -100}
        for mode_name, value in (("Release Test Bank", 60.01), ("Release Test Cash", 39.99)):
            mode = client.get_doc("Mode of Payment", mode_name)
            accounts = [r["default_account"] for r in mode["accounts"] if r["company"] == ctx["company"]]
            if len(accounts) != 1 or accounts[0] in ctx["movements"]:
                raise AssertionError("combined receipt needs distinct configured bank and cash accounts")
            ctx["movements"][accounts[0]] = value
            methods.append({
                "mode_of_payment": mode_name, "amount": value,
                "paid_from": payment["paid_from"], "paid_to": accounts[0],
                "paid_from_account_currency": "ARS", "paid_to_account_currency": "ARS",
            })
        payment.update({
            "doctype": "Payment Entry", "paid_amount": 100, "received_amount": 100,
            "reference_no": ctx["invoice"]["name"],
            "reference_date": ctx["invoice"]["posting_date"], "modes_of_payment": methods,
        })
        ctx["payment"] = client.submit(client.insert(payment))

    def verify(self, client, ctx):
        checks.ledger(client, ctx["payment"]["name"], ctx["movements"])
        invoice = client.get_doc("Sales Invoice", ctx["invoice"]["name"])
        checks.amount(invoice.get("outstanding_amount"), 0, "combined receipt settled debt")
