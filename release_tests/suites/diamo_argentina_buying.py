"""Purchase invoice, partial payment, full settlement and reversal in ARS."""

from decimal import Decimal

from . import diamo_accounting as checks
from .base import ReleaseSuite, Step


class DiamoArgentinaBuyingSuite(ReleaseSuite):
    name = "diamo_argentina_buying"
    required_app = "diamoerp_argentina"
    description = "Purchase for ARS 100.01: pay 40.01 and 60, check ledger and reverse payments. No withholdings."

    def build_steps(self, versions):
        return [
            Step("verify isolated supplier and ARS fixtures", self.prepare),
            Step("submit purchase invoice for ARS 100.01", self.invoice),
            Step("pay 40.01 and verify remaining debt of 60", self.partial),
            Step("pay 60 and verify zero debt", self.settle),
            Step("cancel both payments and restore debt of 100.01", self.cancel),
        ]

    def prepare(self, client, ctx):
        checks.prepare(client, ctx)
        ctx["supplier"] = client.get_doc("Supplier", "Release Test Supplier")["name"]
        mode = client.get_doc("Mode of Payment", "Release Test Bank")
        banks = [
            row["default_account"] for row in mode["accounts"] if row["company"] == ctx["company"]
        ]
        if len(banks) != 1:
            raise AssertionError("Release Test Bank needs exactly one account for the test company")
        ctx["bank"] = banks[0]
        ctx["payments"] = []

    def invoice(self, client, ctx):
        draft = client.insert(
            {
                "doctype": "Purchase Invoice",
                "company": ctx["company"],
                "supplier": ctx["supplier"],
                "currency": "ARS",
                "update_stock": 0,
                "taxes": [],
                "disable_rounded_total": 1,
                "items": [{"item_code": ctx["item"], "qty": 1, "rate": 100.01}],
            }
        )
        ctx["invoice"] = client.submit(draft)
        if ctx["invoice"].get("docstatus") != 1:
            raise AssertionError("purchase invoice must be submitted")
        checks.amount(ctx["invoice"].get("grand_total"), "100.01", "purchase total")
        self.outstanding(client, ctx, "100.01")

    def partial(self, client, ctx):
        self.pay(client, ctx, "40.01")
        self.outstanding(client, ctx, 60)

    def settle(self, client, ctx):
        self.pay(client, ctx, "60")
        self.outstanding(client, ctx, 0)

    def cancel(self, client, ctx):
        for payment, outstanding in zip(reversed(ctx["payments"]), (60, "100.01"), strict=True):
            cancelled = client.cancel("Payment Entry", payment["name"])
            if cancelled.get("docstatus") != 2:
                raise AssertionError("supplier payment must be cancelled")
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
                raise AssertionError("cancelled supplier payment retains active ledger entries")
            self.outstanding(client, ctx, outstanding)

    def pay(self, client, ctx, value):
        payment = client.call(
            "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
            dt="Purchase Invoice",
            dn=ctx["invoice"]["name"],
        )
        if payment.get("payment_type") != "Pay" or payment.get("party") != ctx["supplier"]:
            raise AssertionError("payment must target the test supplier")
        if any(
            payment.get(key) != "ARS"
            for key in ("paid_from_account_currency", "paid_to_account_currency")
        ):
            raise AssertionError("supplier payment accounts must use ARS")
        if payment.get("paid_from") != ctx["bank"]:
            raise AssertionError("proposed bank does not match Release Test Bank")
        references = payment.get("references", [])
        if len(references) != 1 or references[0]["reference_name"] != ctx["invoice"]["name"]:
            raise AssertionError("payment must reference only this run's purchase invoice")
        references[0]["allocated_amount"] = float(value)
        payment.update(
            {
                "doctype": "Payment Entry",
                "paid_amount": float(value),
                "received_amount": float(value),
                "reference_no": ctx["invoice"]["name"],
                "reference_date": ctx["invoice"]["posting_date"],
                "modes_of_payment": [
                    {
                        "mode_of_payment": "Release Test Bank",
                        "amount": float(value),
                        "paid_from": payment["paid_from"],
                        "paid_to": payment["paid_to"],
                        "paid_from_account_currency": "ARS",
                        "paid_to_account_currency": "ARS",
                    }
                ],
            }
        )
        submitted = client.submit(client.insert(payment))
        ctx["payments"].append(submitted)
        if submitted.get("docstatus") != 1:
            raise AssertionError("supplier payment must be submitted")
        checks.ledger(
            client,
            submitted["name"],
            {
                payment["paid_from"]: -Decimal(value),
                payment["paid_to"]: Decimal(value),
            },
        )

    def outstanding(self, client, ctx, expected):
        invoice = client.get_doc("Purchase Invoice", ctx["invoice"]["name"])
        checks.amount(invoice.get("outstanding_amount"), expected, "supplier outstanding")
