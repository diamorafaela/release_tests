"""Argentina receipt, ledger and cancellation through the public API."""

from . import diamo_accounting as checks
from . import diamo_receipt_edges
from .base import ReleaseSuite, Step


class DiamoArgentinaPaymentsSuite(ReleaseSuite):
    name = "diamo_argentina_payments"
    required_app = "diamoerp_argentina"
    description = (
        "ARS receipts: full and partial settlement, cent rounding, multiple invoices, ledger and cancellation."
    )

    def build_steps(self, versions):
        return [
            Step("verify isolated ARS fixtures", checks.prepare),
            Step("submit invoice for ARS 100", checks.invoice),
            Step("verify initial zero payment and enter receipt", self.receive),
            Step("verify bank and receivable ledger", self.verify),
            Step("cancel receipt and restore invoice balance", self.cancel),
            Step("receive 33.33, 33.33 and 33.34 without residual debt", diamo_receipt_edges.partial_receipts),
            Step("cancel earlier receipts, collect again and restore debt", diamo_receipt_edges.reverse_receipts),
            Step("settle two invoices with one receipt and reverse both balances", diamo_receipt_edges.multiple_invoices),
        ]

    def receive(self, client, ctx):
        payment = client.call(
            "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
            dt="Sales Invoice",
            dn=ctx["invoice"]["name"],
        )
        checks.amount(payment.get("paid_amount"), 0, "unconfigured receipt starts at zero")
        checks.amount(payment.get("received_amount"), 0, "received amount starts at zero")
        if any(
            payment.get(field) != "ARS"
            for field in (
                "paid_from_account_currency",
                "paid_to_account_currency",
            )
        ):
            raise AssertionError("receipt accounts must both use ARS")
        mode = client.get_doc("Mode of Payment", "Release Test Bank")
        accounts = [
            row["default_account"] for row in mode["accounts"] if row["company"] == ctx["company"]
        ]
        if accounts != [payment["paid_to"]]:
            raise AssertionError("Release Test Bank must match the proposed bank account")
        payment.update(
            {
                "doctype": "Payment Entry",
                "paid_amount": 100,
                "received_amount": 100,
                "reference_no": ctx["invoice"]["name"],
                "reference_date": ctx["invoice"]["posting_date"],
                "modes_of_payment": [
                    {
                        "mode_of_payment": mode["name"],
                        "amount": 100,
                        "paid_from": payment["paid_from"],
                        "paid_to": payment["paid_to"],
                        "paid_from_account_currency": "ARS",
                        "paid_to_account_currency": "ARS",
                    }
                ],
            }
        )
        ctx["payment"] = client.submit(client.insert(payment))

    def verify(self, client, ctx):
        payment = ctx["payment"]
        if payment.get("docstatus") != 1:
            raise AssertionError("receipt must be submitted")
        checks.ledger(
            client, payment["name"], {payment["paid_to"]: 100, payment["paid_from"]: -100}
        )
        invoice = client.get_doc("Sales Invoice", ctx["invoice"]["name"])
        checks.amount(invoice.get("outstanding_amount"), 0, "settled invoice")

    def cancel(self, client, ctx):
        payment = client.cancel("Payment Entry", ctx["payment"]["name"])
        if payment.get("docstatus") != 2:
            raise AssertionError("receipt must be cancelled")
        active = client.get_list(
            "GL Entry",
            filters={
                "voucher_type": "Payment Entry",
                "voucher_no": payment["name"],
                "is_cancelled": 0,
            },
            limit=1,
        )
        if active:
            raise AssertionError("cancelled receipt still has active ledger entries")
        invoice = client.get_doc("Sales Invoice", ctx["invoice"]["name"])
        checks.amount(invoice.get("outstanding_amount"), 100, "restored invoice balance")


class DiamoHRMSPaymentsSuite(DiamoArgentinaPaymentsSuite):
    name = "diamo_hrms_payments"
    required_app = "hrms"
    description = (
        "Argentina receipt and cancellation with HRMS installed: verify controller compatibility."
    )

    def applies(self, versions):
        return all(app in versions for app in ("hrms", "erpnext", "diamoerp_argentina"))
