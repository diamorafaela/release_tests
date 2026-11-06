"""Read-only checks of the prerequisites owned by the local QA setup."""

import frappe

from . import COMPANY, DEFAULT_SUITES


class Preflight:
    def __init__(self, suites, user):
        self.suites = set(suites)
        self.user = user
        self.blockers = []

    def run(self):
        from release_tests.api import catalog

        installed = set(frappe.get_installed_apps())
        for entry in catalog():
            if entry["suite"] in self.suites and entry["required_app"] not in installed:
                self.blockers.append(f"{entry['suite']}: install {entry['required_app']} or remove the suite.")
        unsupported = self.suites - set(DEFAULT_SUITES) - {"customisations", "diamo_hrms_payments"}
        if unsupported:
            self.blockers.append("Prerequisites not yet covered by this checker: " + ", ".join(sorted(unsupported)))
        self.check_identity()
        if self.suites - {"core_frappe", "frappe_filters", "customisations"}:
            if "erpnext" in installed:
                self.check_accounting()
            else:
                self.blockers.append("ERPNext is required for the accounting fixtures.")
        if "frappe_filters" in self.suites or "customisations" in self.suites:
            self.check_scripts()
        if "customisations" in self.suites:
            self.permission("Custom Field", "create")
            self.permission("Client Script", "create")
            self.permission("Server Script", "create")
        if "diamo_base_access" in self.suites and "diamoerp_base" in installed:
            self.check_slots()
        return {"site": frappe.local.site, "user": self.user, "suites": sorted(self.suites),
                "ready": not self.blockers, "blockers": self.blockers,
                "notes": ["Readiness is not a test result. Run the selected suites after preparation.",
                          "Use the same suites and executor in Testing Site. Customisations also requires Allow Customisations."]}

    def check_identity(self):
        if not self.exists("User", self.user):
            return
        user = frappe.get_doc("User", self.user)
        if not user.enabled:
            self.blockers.append(f"User {self.user} is disabled.")
        if self.user != "Administrator":
            if not user.get("enable_api_access"):
                self.blockers.append(f"{self.user} must be a dedicated API user for token authentication.")
            if not user.api_key or not user.get_password("api_secret", raise_exception=False):
                self.blockers.append(f"Generate API credentials for {self.user} and configure Testing Site.")
        if "System Manager" not in frappe.get_roles(self.user):
            self.blockers.append("The executor needs System Manager to inspect the release environment.")
        if "core_frappe" in self.suites or "frappe_filters" in self.suites:
            self.permission("ToDo", "create")
        if "crm" in self.suites:
            for doctype in ("CRM Lead", "CRM Deal"):
                self.permission(doctype, "create")
        if "diamo_base_access" in self.suites:
            self.permission("User", "create")
        if self.suites & {"hrms", "hrms_org", "hrms_leave", "hrms_expense"}:
            self.permission("Employee", "create")

    def check_accounting(self):
        if not self.exists("Company", COMPANY):
            return
        company = frappe.get_doc("Company", COMPANY)
        if company.default_currency != "ARS":
            self.blockers.append(f"{COMPANY} must use ARS.")
        for field in ("default_bank_account", "default_cash_account", "default_receivable_account",
                      "default_payable_account", "default_income_account", "default_expense_account", "cost_center"):
            if not company.get(field):
                self.blockers.append(f"Company is missing {field}.")
        for doctype, name in (("Customer", "Release Test Customer"), ("Supplier", "Release Test Supplier"),
                              ("Item", "RT-ITEM"), ("Mode of Payment", "Release Test Bank"),
                              ("Mode of Payment", "Release Test Cash")):
            self.exists(doctype, name)
        if frappe.db.exists("Item", "RT-ITEM"):
            item = frappe.get_doc("Item", "RT-ITEM")
            if item.is_stock_item or item.is_fixed_asset or item.disabled:
                self.blockers.append("RT-ITEM must be an enabled non-stock service.")
        for dt, name, table in (("Customer", "Release Test Customer", "impuestos_de_percepcion"),
                                ("Supplier", "Release Test Supplier", "impuestos_de_retencion")):
            if frappe.db.exists(dt, name) and frappe.get_doc(dt, name).get(table):
                self.blockers.append(f"{name} must have no automatic fiscal taxes for the basic circuit.")
        for kind, field in (("Bank", "default_bank_account"), ("Cash", "default_cash_account")):
            name = f"Release Test {kind}"
            if frappe.db.exists("Mode of Payment", name):
                payment = frappe.get_doc("Mode of Payment", name)
                rows = [row for row in payment.accounts if row.company == COMPANY]
                if not payment.enabled or len(rows) != 1 or rows[0].default_account != company.get(field):
                    self.blockers.append(f"{name} must be enabled and match the company's {field}.")
        for dt in ("Customer", "Supplier", "Item"):
            self.permission(dt, "read")
            self.permission(dt, "create")
        for dt in ("Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry"):
            for action in ("read", "create", "write", "submit", "cancel"):
                self.permission(dt, action)
        self.permission("GL Entry", "read")
        if self.suites & {"erpnext_stock", "erpnext_buying", "erpnext_selling", "erpnext_batched",
                          "erpnext_serialised", "erpnext_manufacturing"}:
            for field in ("default_inventory_account", "stock_received_but_not_billed", "stock_adjustment_account"):
                if not company.get(field):
                    self.blockers.append(f"Company is missing {field}.")
        if self.suites & {"diamo_perceptions", "diamo_withholdings"}:
            self.check_fiscal(company)

    def check_fiscal(self, company):
        if "diamo_perceptions" in self.suites:
            if not company.get("agente_de_percepcion"):
                self.blockers.append("Enable perception agent on the test company.")
            for dt, name in (("Customer", "Release Test Fiscal Customer"),
                             ("Impuesto de Percepcion", "Release Test IVA 3%"),
                             ("Punto de Venta", "Release Test Manual")):
                self.exists(dt, name)
            self.verify_fields("Impuesto de Percepcion", "Release Test IVA 3%", {
                "company": COMPANY, "categoria": "IVA", "alicuota": 3, "minimo_imponible": 100,
            })
            self.verify_fields("Punto de Venta", "Release Test Manual", {
                "company": COMPANY, "tipo": "Manual", "habilitado": 1, "no_usar_plantilla_impuestos": 1,
            })
            self.verify_tax_link("Customer", "Release Test Fiscal Customer", "impuestos_de_percepcion",
                                 "impuesto_percepcion", "Release Test IVA 3%")
        if "diamo_withholdings" in self.suites:
            if not company.get("agente_retencion_iibb"):
                self.blockers.append("Enable IIBB withholding agent on the test company.")
            self.exists("Supplier", "Release Test Fiscal Supplier")
            self.exists("Impuesto de Retencion", "Release Test IIBB 2.5%")
            self.verify_fields("Impuesto de Retencion", "Release Test IIBB 2.5%", {
                "company": COMPANY, "categoria": "Ingresos Brutos", "jurisdiccion": "MENDOZA",
                "alicuota": 2.5, "minimo_imponible": 100, "base_imponible": "Neto",
                "tipo_de_calculo": "Por Monto de Pago",
            })
            self.verify_tax_link("Supplier", "Release Test Fiscal Supplier", "impuestos_de_retencion",
                                 "impuesto_retencion", "Release Test IIBB 2.5%")
            if "DRT-APERTURA-COMPRA-" not in frappe.get_meta("Purchase Invoice").get_field("naming_series").options.splitlines():
                self.blockers.append("Purchase Invoice is missing the DRT-APERTURA-COMPRA- naming series.")
            # Payment submission creates Retencion internally with ignore_permissions=True.
            for action in ("read", "write", "submit", "cancel"):
                self.permission("Retencion", action)

    def verify_fields(self, doctype, name, expected):
        if not frappe.db.exists("DocType", doctype) or not frappe.db.exists(doctype, name):
            return
        doc = frappe.get_doc(doctype, name)
        for field, value in expected.items():
            if doc.get(field) != value:
                self.blockers.append(f"{name}: {field} must be {value}.")

    def verify_tax_link(self, doctype, name, table, field, tax):
        if not frappe.db.exists(doctype, name):
            return
        doc = frappe.get_doc(doctype, name)
        if not any(row.get(field) == tax and row.company == COMPANY for row in doc.get(table, [])):
            self.blockers.append(f"{name}: missing tax assignment {tax} for {COMPANY}.")

    def check_scripts(self):
        from release_tests.customisations import RT_API_SCRIPT, _fixture

        if not frappe.get_common_site_config().get("server_script_enabled"):
            self.blockers.append("Enable server_script_enabled in common_site_config.json, then run prepare again.")
        if self.exists("Server Script", RT_API_SCRIPT):
            script = frappe.get_doc("Server Script", RT_API_SCRIPT)
            expected = next(row for row in _fixture("server_scripts.json") if row["name"] == RT_API_SCRIPT)
            if script.disabled or any(script.get(key) != expected[key] for key in ("script", "api_method", "script_type")):
                self.blockers.append("RT Filter Probe differs from the engine fixture or is disabled; review it before rerunning.")

    def check_slots(self):
        from diamoerp_base.limits import get_limits
        from diamoerp_base.overrides.user import (
            get_api_user_limit, get_enabled_api_users, get_enabled_erp_users,
            get_enabled_system_users, get_erp_user_limit,
        )

        limits = get_limits()
        if get_api_user_limit(limits) - len(get_enabled_api_users()) < 1:
            self.blockers.append("diamo_base_access needs one free API slot in addition to the QA executor.")
        if limits.get("users") and get_erp_user_limit(limits) - len(get_enabled_erp_users()) < 1:
            self.blockers.append("diamo_base_access needs one free ERP slot for its API-to-Desk conversion.")
        reduced = "Usuario Reducido de Proyecto"
        self.exists("User Type", reduced)
        limit = limits.get(frappe.scrub(reduced))
        if limit is not None and limit - len(get_enabled_system_users(reduced)) < 1:
            self.blockers.append("diamo_base_access needs one free reduced-project-user slot.")

    def exists(self, doctype, name):
        if not frappe.db.exists("DocType", doctype) or not frappe.db.exists(doctype, name):
            self.blockers.append(f"Missing {doctype}: {name}.")
            return False
        return True

    def permission(self, doctype, action):
        if not frappe.db.exists("User", self.user):
            return
        if "diamoerp_base" in frappe.get_installed_apps() and self.user != "Administrator":
            from diamoerp_base.permissions import ONLY_ADMINISTRATOR_DOCTYPES

            if doctype in ONLY_ADMINISTRATOR_DOCTYPES:
                self.blockers.append(f"{doctype} is restricted to Administrator by Base; QA roles cannot grant {action}.")
                return
        if not frappe.db.exists("DocType", doctype):
            self.blockers.append(f"Missing DocType: {doctype}.")
        elif not frappe.has_permission(doctype, ptype=action, user=self.user):
            self.blockers.append(f"{self.user}: missing {action} permission on {doctype}.")
