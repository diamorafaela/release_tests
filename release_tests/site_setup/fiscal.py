import frappe

from . import COMPANY
from .fixtures import ensure, ensure_child


def prepare_fiscal(company, accounts):
    for field in ("agente_de_percepcion", "agente_retencion_iibb"):
        company.set(field, 1)
    company.save()
    common = {
        "company": COMPANY, "cuenta_de_venta": accounts["Tax"],
        "centro_de_costos": company.cost_center, "minimo_imponible": 100,
    }
    perception = {**common, "nombre": "Release Test IVA 3%", "categoria": "IVA",
                  "alicuota": 3, "percepcion_minima": 1}
    ensure("Impuesto de Percepcion", perception["nombre"], perception, verify=tuple(perception))
    withholding = {**common, "nombre": "Release Test IIBB 2.5%", "categoria": "Ingresos Brutos",
                   "jurisdiccion": "MENDOZA", "cuenta_de_compra": accounts["Tax"],
                   "alicuota": 2.5, "base_imponible": "Neto", "tipo_de_calculo": "Por Monto de Pago",
                   "retencion_minima": 1}
    ensure("Impuesto de Retencion", withholding["nombre"], withholding, verify=tuple(withholding))
    for doctype, source, name, table, field, tax in (
        ("Customer", "Release Test Customer", "Release Test Fiscal Customer",
         "impuestos_de_percepcion", "impuesto_percepcion", perception["nombre"]),
        ("Supplier", "Release Test Supplier", "Release Test Fiscal Supplier",
         "impuestos_de_retencion", "impuesto_retencion", withholding["nombre"]),
    ):
        original = frappe.get_doc(doctype, source)
        prefix = doctype.lower()
        values = {f"{prefix}_name": name, f"{prefix}_type": "Company",
                  f"{prefix}_group": original.get(f"{prefix}_group")}
        if doctype == "Customer":
            values["territory"] = original.territory
        party = ensure(doctype, name, values)
        ensure_child(party, table, field, tax, {"company": COMPANY, field: tax})
        party.save()
    pos = ensure("Punto de Venta", "Release Test Manual", {
        "company": COMPANY, "tipo": "Manual", "habilitado": 1, "no_usar_plantilla_impuestos": 1,
        "ws_afip": "Mercado interno -sin detalle- RG2485 (WSFEv1)",
    }, verify=("company", "tipo", "habilitado", "no_usar_plantilla_impuestos"))
    ensure_child(pos, "secuencias", "secuencia", "ACC-SINV-.YYYY.-", {"secuencia": "ACC-SINV-.YYYY.-"})
    pos.save()
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    options = frappe.get_meta("Purchase Invoice").get_field("naming_series").options or ""
    series = "DRT-APERTURA-COMPRA-"
    if series not in options.splitlines():
        make_property_setter("Purchase Invoice", "naming_series", "options",
                             options.rstrip() + "\n" + series, "Text")
