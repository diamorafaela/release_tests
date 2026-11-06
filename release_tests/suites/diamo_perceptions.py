"""Local IVA perceptions on manual-POS drafts; no fiscal submission."""

import json

from . import diamo_accounting as checks
from .base import CheckFailed, ReleaseSuite, Step


class DiamoPerceptionsSuite(ReleaseSuite):
    name = "diamo_perceptions"
    required_app = "diamoerp_argentina"
    description = "IVA perception 3%: rounding, repeated save, quantity changes and crossing the minimum base. Drafts only."

    def build_steps(self, versions):
        return [
            Step("verify local perception fixtures", self.prepare),
            Step("calculate perception of 30 on net 1000", self.invoice),
            Step("save again without duplicate perception", self.repeat),
            Step("double quantity and recalculate perception to 60", self.recalculate),
            Step("exclude new invoice below taxable minimum", self.below_minimum),
            Step("perception minimum includes 100 but excludes 99.99", self.minimum_boundary),
            Step("round fractional perception and preserve it on repeated save", self.fractional_tax),
            Step("remove and restore perception when crossing taxable minimum", self.cross_minimum),
        ]

    def prepare(self, client, ctx):
        checks.prepare(client, ctx)
        company = client.get_doc("Company", ctx["company"])
        if not company.get("agente_de_percepcion"):
            raise AssertionError("test company must be a perception agent")
        ctx["customer"] = client.get_doc("Customer", "Release Test Fiscal Customer")["name"]
        tax = client.get_doc("Impuesto de Percepcion", "Release Test IVA 3%")
        checks.amount(tax.get("alicuota"), 3, "fixture perception rate")
        checks.amount(tax.get("minimo_imponible"), 100, "fixture minimum base")
        if tax.get("categoria") != "IVA" or tax.get("company") != ctx["company"]:
            raise AssertionError("perception must use local IVA and the test company")
        ctx["tax"] = tax
        pos = client.get_doc("Punto de Venta", "Release Test Manual")
        if pos.get("tipo") != "Manual" or not pos.get("habilitado"):
            raise AssertionError("enabled manual point of sale required")
        ctx["pos"] = pos["name"]

    def invoice(self, client, ctx):
        ctx["invoice"] = self.draft(client, ctx, 1000)
        self.verify(ctx, 30, 1030)

    def repeat(self, client, ctx):
        ctx["invoice"] = client.call("frappe.client.save", doc=json.dumps(ctx["invoice"]))
        self.verify(ctx, 30, 1030)

    def recalculate(self, client, ctx):
        ctx["invoice"]["items"][0]["qty"] = 2
        ctx["invoice"] = client.call("frappe.client.save", doc=json.dumps(ctx["invoice"]))
        self.verify(ctx, 60, 2060)

    def below_minimum(self, client, ctx):
        invoice = self.draft(client, ctx, 50)
        if invoice.get("taxes"):
            raise AssertionError("below-minimum invoice must not have perception taxes")
        checks.amount(invoice.get("grand_total"), 50, "below-minimum total")

    def minimum_boundary(self, client, ctx):
        invoice = self.draft(client, ctx, 99.99)
        if invoice.get("taxes"):
            raise AssertionError("99.99 is below the perception minimum of 100")
        checks.amount(invoice.get("grand_total"), "99.99", "just below minimum total")
        boundary = {**ctx, "invoice": self.draft(client, ctx, 100)}
        self.verify(boundary, 3, 103)

    def fractional_tax(self, client, ctx):
        fractional = {**ctx, "invoice": self.draft(client, ctx, 100.25)}
        self.verify(fractional, "3.01", "103.26")
        for _ in range(2):
            fractional["invoice"] = client.call("frappe.client.save", doc=json.dumps(fractional["invoice"]))
            self.verify(fractional, "3.01", "103.26")

    def cross_minimum(self, client, ctx):
        changing = {**ctx, "invoice": self.draft(client, ctx, 100)}
        self.verify(changing, 3, 103)
        for rate, tax, total in ((99.99, 0, 99.99), (100, 3, 103), (99.99, 0, 99.99)):
            changing["invoice"]["items"][0]["rate"] = rate
            changing["invoice"] = client.call("frappe.client.save", doc=json.dumps(changing["invoice"]))
            if tax:
                self.verify(changing, tax, total)
            else:
                if changing["invoice"].get("taxes"):
                    raise CheckFailed(
                        "lowering the taxable base must remove the perception row",
                        expected="no perception below taxable base 100",
                        actual=f"net={changing['invoice'].get('net_total')}, total={changing['invoice'].get('grand_total')}",
                        hint="Review perception removal when an existing invoice crosses the minimum base.",
                    )
                checks.amount(changing["invoice"].get("grand_total"), total, "recalculated below minimum total")

    def draft(self, client, ctx, rate):
        return client.insert({
            "doctype": "Sales Invoice", "company": ctx["company"], "customer": ctx["customer"],
            "currency": "ARS", "punto_de_venta": ctx["pos"], "naming_series": "ACC-SINV-.YYYY.-",
            "disable_rounded_total": 1, "taxes": [],
            "items": [{"item_code": ctx["item"], "qty": 1, "rate": rate}],
        })

    def verify(self, ctx, expected_tax, total):
        invoice = ctx["invoice"]
        taxes = invoice.get("taxes", [])
        if invoice.get("docstatus") != 0 or len(taxes) != 1:
            raise AssertionError("draft must have exactly one perception row")
        tax = taxes[0]
        if tax.get("impuesto_de_percepcion") != ctx["tax"]["name"]:
            raise AssertionError("wrong perception definition")
        if tax.get("account_head") != ctx["tax"]["cuenta_de_venta"]:
            raise AssertionError("wrong perception account")
        checks.amount(tax.get("rate"), 3, "perception rate")
        checks.amount(tax.get("tax_amount"), expected_tax, "perception amount")
        checks.amount(invoice.get("grand_total"), total, "perception invoice total")
