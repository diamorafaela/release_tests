"""Local control-site installation of the curated Diamo regression profile."""

from .diamo_contracts import CORE_SUITES


def install_diamo():
    import frappe
    from release_manager.api import sync_catalog

    from .site_setup import require_administrator

    require_administrator()
    name = "Diamo Forks"
    sync_catalog()
    cases = {row.suite: row.name for row in frappe.get_all(
        "Release Test Case", filters={"suite": ["in", list(CORE_SUITES)], "enabled": 1}, fields=["name", "suite"])}
    if set(cases) != set(CORE_SUITES):
        frappe.throw("Enable the missing Diamo Forks test cases before installing the profile: "
                     + ", ".join(sorted(set(CORE_SUITES) - set(cases))))
    if frappe.db.exists("Test Case Group", name):
        group = frappe.get_doc("Test Case Group", name)
        if {row.test_case for row in group.test_cases} != set(cases.values()) or not group.enabled:
            frappe.throw("Diamo Forks differs from the shipped profile. Review its cases before updating it.")
    else:
        frappe.get_doc({"doctype": "Test Case Group", "group_name": name, "enabled": 1,
                       "description": "Diamo Base/Argentina behavior across Frappe and ERPNext upgrades.",
                       "test_cases": [{"test_case": cases[suite]} for suite in CORE_SUITES]}).insert()
    return {"profile": name, "suites": list(CORE_SUITES)}
