"""Deterministic, local accounting masters for the Diamo suites."""

import frappe

from . import COMPANY

ABBR = "DRT"


class AccountingFixtures:
    def prepare(self, fiscal=False):
        self.company = ensure("Company", COMPANY, {
            "company_name": COMPANY, "abbr": ABBR, "country": "Argentina",
            "default_currency": "ARS", "create_chart_of_accounts_based_on": "Standard Template",
            "chart_of_accounts": "Standard with Numbers",
        }, verify=("default_currency", "abbr"))
        self.accounts = self.create_accounts()
        for field, value in {
            "default_bank_account": self.accounts["Bank"],
            "default_cash_account": self.accounts["Cash"],
            "default_receivable_account": self.accounts["Receivable"],
            "default_payable_account": self.accounts["Payable"],
            "default_income_account": self.accounts["Income Account"],
            "default_expense_account": self.accounts["Expense Account"],
        }.items():
            set_missing(self.company, field, value)
        self.company.save()
        self.create_parties()
        ensure("Item", "RT-ITEM", {
            "item_code": "RT-ITEM", "item_name": "Release Test Service", "is_stock_item": 0,
            "is_fixed_asset": 0, "item_group": "All Item Groups", "stock_uom": "Nos",
            "standard_rate": 100,
        }, verify=("is_stock_item", "is_fixed_asset"))
        self.create_payments()
        if fiscal and "diamoerp_argentina" in frappe.get_installed_apps():
            from .fiscal import prepare_fiscal

            prepare_fiscal(self.company, self.accounts)

    def create_accounts(self):
        result = {}
        defaults = {
            "Bank": "default_bank_account", "Cash": "default_cash_account",
            "Receivable": "default_receivable_account", "Payable": "default_payable_account",
            "Income Account": "default_income_account", "Expense Account": "default_expense_account",
        }
        for kind, root in {
            "Bank": "Asset", "Cash": "Asset", "Receivable": "Asset", "Payable": "Liability",
            "Income Account": "Income", "Expense Account": "Expense", "Tax": "Liability",
        }.items():
            existing = self.company.get(defaults.get(kind, ""))
            if existing:
                account = frappe.get_doc("Account", existing)
                if account.company != COMPANY or account.is_group or account.account_currency != "ARS":
                    frappe.throw(f"Invalid company default account: {existing}.")
                result[kind] = existing
                continue
            parent = frappe.db.get_value("Account", {
                "company": COMPANY, "root_type": root, "is_group": 1,
            }, "name", order_by="lft asc")
            if not parent:
                frappe.throw(f"Missing {root} account group for {COMPANY}.")
            label = "Release Test Taxes" if kind == "Tax" else f"Release Test {kind}"
            doc = ensure("Account", f"{label} - {ABBR}", {
                "account_name": label, "company": COMPANY, "parent_account": parent,
                "account_type": kind, "account_currency": "ARS", "is_group": 0,
            }, verify=("company", "account_type", "account_currency", "is_group"))
            result[kind] = doc.name
        return result

    def create_parties(self):
        territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
        if not territory:
            territory = ensure("Territory", "Release Test Territory", {
                "territory_name": "Release Test Territory", "is_group": 0,
                "parent_territory": "All Territories",
            }).name
        customer = ensure("Customer", "Release Test Customer", {
            "customer_name": "Release Test Customer", "customer_type": "Company",
            "customer_group": "All Customer Groups", "territory": territory,
        })
        supplier = ensure("Supplier", "Release Test Supplier", {
            "supplier_name": "Release Test Supplier", "supplier_type": "Company",
            "supplier_group": "All Supplier Groups",
        })
        for doc, kind in ((customer, "Receivable"), (supplier, "Payable")):
            ensure_child(doc, "accounts", "company", COMPANY, {
                "company": COMPANY, "account": self.accounts[kind],
            })
            doc.save()

    def create_payments(self):
        for kind in ("Bank", "Cash"):
            doc = ensure("Mode of Payment", f"Release Test {kind}", {
                "mode_of_payment": f"Release Test {kind}", "type": kind, "enabled": 1,
            }, verify=("type", "enabled"))
            ensure_child(doc, "accounts", "company", COMPANY, {
                "company": COMPANY, "default_account": self.accounts[kind],
            })
            doc.save()


def ensure(doctype, name, values, verify=()):
    if frappe.db.exists(doctype, name):
        doc = frappe.get_doc(doctype, name)
        for field in verify:
            if doc.get(field) != values[field]:
                frappe.throw(f"Fixture conflict: {doctype} {name}, field {field}.")
        return doc
    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.name = name
    doc.insert()
    if doc.name != name:
        frappe.throw(f"Fixture must be named {name}; naming rules produced {doc.name}.")
    return doc


def set_missing(doc, field, value):
    if not doc.get(field):
        doc.set(field, value)


def ensure_child(doc, field, key, value, row):
    existing = next((item for item in doc.get(field, []) if item.get(key) == value), None)
    if existing:
        if any(existing.get(name) != expected for name, expected in row.items()):
            frappe.throw(f"Fixture conflict: {doc.doctype} {doc.name}, table {field}.")
    else:
        doc.append(field, row)
