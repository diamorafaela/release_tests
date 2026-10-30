"""Local IIBB withholding, supplier payment and reversal."""

import json

from . import diamo_accounting as checks
from .base import ReleaseSuite, Step


class DiamoWithholdingsSuite(ReleaseSuite):
    name = "diamo_withholdings"
    required_app = "diamoerp_argentina"
    description = "Opening purchase 1000.25: IIBB 2.5% = 25.01, bank 975.24, settlement and reversal."

    def build_steps(self, versions):
        return [
            Step("verify local withholding fixtures", self.prepare),
            Step("submit opening purchase and prepare payment", self.invoice),
            Step("exclude partial allocation below minimum base", self.below_minimum),
            Step("calculate IIBB base 1000.25 and rounded withholding 25.01", self.calculate),
            Step("apply withholding and submit net payment 975.24", self.pay),
            Step("verify retention document, accounts and settled debt", self.verify),
            Step("cancel payment and retention and restore debt", self.cancel),
        ]

    def prepare(self, client, ctx):
        checks.prepare(client, ctx)
        company = client.get_doc("Company", ctx["company"])
        if not company.get("agente_retencion_iibb"):
            raise AssertionError("test company must be an IIBB withholding agent")
        ctx["supplier"] = client.get_doc("Supplier", "Release Test Fiscal Supplier")["name"]
        tax = client.get_doc("Impuesto de Retencion", "Release Test IIBB 2.5%")
        for field, value in {"company": ctx["company"], "jurisdiccion": "MENDOZA",
                             "categoria": "Ingresos Brutos", "base_imponible": "Neto",
                             "tipo_de_calculo": "Por Monto de Pago"}.items():
            if tax.get(field) != value:
                raise AssertionError(f"invalid local withholding fixture: {field}")
        checks.amount(tax.get("alicuota"), 2.5, "fixture withholding rate")
        checks.amount(tax.get("minimo_imponible"), 100, "fixture withholding minimum base")
        ctx["tax"] = tax

    def invoice(self, client, ctx):
        draft = client.insert({
            "doctype": "Purchase Invoice", "company": ctx["company"], "supplier": ctx["supplier"],
            "naming_series": "DRT-APERTURA-COMPRA-", "currency": "ARS", "taxes": [],
            "disable_rounded_total": 1,
            "items": [{"item_code": ctx["item"], "qty": 1, "rate": 1000.25}],
        })
        ctx["invoice"] = client.submit(draft)
        checks.amount(ctx["invoice"].get("grand_total"), 1000.25, "opening purchase")
        payment = client.call(
            "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
            dt="Purchase Invoice", dn=ctx["invoice"]["name"],
        )
        payment.update({
            "doctype": "Payment Entry", "paid_amount": 1000.25, "received_amount": 1000.25,
            "reference_no": ctx["invoice"]["name"], "reference_date": ctx["invoice"]["posting_date"],
            "modes_of_payment": [{
                "mode_of_payment": "Release Test Bank", "amount": 1000.25,
                "paid_from": payment["paid_from"], "paid_to": payment["paid_to"],
                "paid_from_account_currency": "ARS", "paid_to_account_currency": "ARS",
            }],
        })
        ctx["payment"] = client.insert(payment)

    def below_minimum(self, client, ctx):
        payment = ctx["payment"]
        payment["references"][0]["allocated_amount"] = 50
        payment["paid_amount"] = payment["received_amount"] = 50
        payment["modes_of_payment"][0]["amount"] = 50
        payment = client.call("frappe.client.save", doc=json.dumps(payment))
        result = client.call("diamoerp_argentina.retenciones.generar_retenciones",
                             entrada_de_pago=payment["name"])
        if result.get("iibb") or result.get("ganancias"):
            raise AssertionError("allocation below minimum must not generate withholding")
        payment["references"][0]["allocated_amount"] = 1000.25
        payment["paid_amount"] = payment["received_amount"] = 1000.25
        payment["modes_of_payment"][0]["amount"] = 1000.25
        ctx["payment"] = client.call("frappe.client.save", doc=json.dumps(payment))

    def calculate(self, client, ctx):
        result = client.call("diamoerp_argentina.retenciones.generar_retenciones",
                             entrada_de_pago=ctx["payment"]["name"])
        if set(result.get("iibb") or {}) != {"MENDOZA"} or result.get("ganancias"):
            raise AssertionError("expected only the configured local IIBB withholding")
        tax = result["iibb"]["MENDOZA"]
        if tax.get("impuesto") != ctx["tax"]["name"]:
            raise AssertionError("wrong withholding definition")
        checks.amount(tax.get("base"), 1000.25, "withholding taxable base")
        checks.amount(tax.get("alicuota"), 2.5, "withholding rate")
        checks.amount(tax.get("monto_retenido"), 25.01, "rounded withholding")

    def pay(self, client, ctx):
        payment = ctx["payment"]
        payment["retenciones"] = [{
            "retencion": ctx["tax"]["name"], "categoria": "Ingresos Brutos",
            "base": 1000.25, "alicuota": 2.5, "monto": 25.01,
        }]
        payment = client.call("frappe.client.save", doc=json.dumps(payment))
        payment["deductions"] = [{
            "account": ctx["tax"]["cuenta_de_compra"], "amount": -25.01,
            "cost_center": ctx["tax"]["centro_de_costos"],
            "retencion": payment["retenciones"][0]["name"],
        }]
        payment["paid_amount"] = payment["received_amount"] = 975.24
        payment["modes_of_payment"][0]["amount"] = 975.24
        ctx["payment"] = client.submit(client.call("frappe.client.save", doc=json.dumps(payment)))

    def verify(self, client, ctx):
        payment = client.get_doc("Payment Entry", ctx["payment"]["name"])
        checks.amount(payment.get("numerado_total"), 1000.25, "gross payment")
        checks.ledger(client, payment["name"], {
            payment["paid_from"]: -975.24, payment["paid_to"]: 1000.25,
            ctx["tax"]["cuenta_de_compra"]: -25.01,
        })
        retention = client.get_doc("Retencion", payment["retenciones"][0]["retencion_name"])
        ctx["retention"] = retention["name"]
        if retention.get("docstatus") != 1 or retention.get("retencion") != ctx["tax"]["name"]:
            raise AssertionError("linked retention must be submitted with the expected tax")
        checks.amount(retention.get("monto"), 25.01, "retention certificate amount")
        checks.amount(client.get_doc("Purchase Invoice", ctx["invoice"]["name"]).get("outstanding_amount"),
                      0, "withholding payment settled debt")

    def cancel(self, client, ctx):
        client.cancel("Payment Entry", ctx["payment"]["name"])
        if client.get_doc("Retencion", ctx["retention"]).get("docstatus") != 2:
            raise AssertionError("linked retention must be cancelled")
        active = client.get_list("GL Entry", filters={"voucher_type": "Payment Entry",
                                 "voucher_no": ctx["payment"]["name"], "is_cancelled": 0}, limit=1)
        if active:
            raise AssertionError("cancelled withholding payment retains active ledger entries")
        checks.amount(client.get_doc("Purchase Invoice", ctx["invoice"]["name"]).get("outstanding_amount"),
                      1000.25, "restored supplier debt")
