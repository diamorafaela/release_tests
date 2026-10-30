"""Suite registry.

Suites are listed in execution order. ``core_frappe`` runs first (it proves the
basics), then ERPNext/HRMS, then the gated stub suites which auto-skip when their
app isn't installed.
"""

from __future__ import annotations

from .base import ReleaseSuite


def all_suites() -> list[ReleaseSuite]:
    # Imported lazily so importing the package never requires every submodule.
    from . import (
        builder,
        core_frappe,
        crm,
        customisations,
        diamo_argentina_payments,
        diamo_argentina_buying,
        diamo_base_access,
        diamo_combined_receipts,
        diamo_perceptions,
        diamo_withholdings,
        diamo_service_credits,
        erpnext,
        erpnext_accounts,
        erpnext_batched,
        erpnext_buying,
        erpnext_manufacturing,
        erpnext_selling,
        erpnext_serialised,
        erpnext_service,
        erpnext_stock,
        frappe_filters,
        frappe_jinja_sandbox,
        frappe_permissions,
        helpdesk,
        hrms,
        hrms_expense,
        hrms_leave,
        hrms_org,
        india_compliance,
        insights,
        ksa_compliance,
        learning,
        v16p_erpnext,
        v16p_frappe_features,
        v16p_hrms,
        v16p_hrms_security,
        v16p_security,
        v16p_upgrade_checks,
        webshop,
    )

    return [
        core_frappe.CoreFrappeSuite(),
        diamo_argentina_payments.DiamoArgentinaPaymentsSuite(),
        diamo_argentina_buying.DiamoArgentinaBuyingSuite(),
        diamo_combined_receipts.DiamoCombinedReceiptsSuite(),
        diamo_perceptions.DiamoPerceptionsSuite(),
        diamo_withholdings.DiamoWithholdingsSuite(),
        diamo_base_access.DiamoBaseAccessSuite(),
        diamo_argentina_payments.DiamoHRMSPaymentsSuite(),
        diamo_service_credits.DiamoServiceCreditsSuite(),
        frappe_filters.FrappeFiltersSuite(),
        frappe_jinja_sandbox.FrappeJinjaSandboxSuite(),
        frappe_permissions.FrappePermissionsSuite(),
        erpnext.ERPNextSuite(),
        erpnext_selling.ERPNextSellingSuite(),
        erpnext_buying.ERPNextBuyingSuite(),
        erpnext_stock.ERPNextStockSuite(),
        erpnext_accounts.ERPNextAccountsSuite(),
        erpnext_service.ERPNextServiceSuite(),
        erpnext_serialised.ERPNextSerialisedSuite(),
        erpnext_batched.ERPNextBatchedSuite(),
        erpnext_manufacturing.ERPNextManufacturingSuite(),
        hrms.HRMSSuite(),
        hrms_org.HRMSOrgSuite(),
        hrms_leave.HRMSLeaveSuite(),
        hrms_expense.HRMSExpenseSuite(),
        crm.CRMSuite(),
        helpdesk.HelpdeskSuite(),
        learning.LearningSuite(),
        insights.InsightsSuite(),
        builder.BuilderSuite(),
        webshop.WebshopSuite(),
        india_compliance.IndiaComplianceSuite(),
        ksa_compliance.KSAComplianceSuite(),
        customisations.CustomisationsSuite(),
        # version-16-polished release suites; skip on any site that isn't polished.
        v16p_upgrade_checks.V16PUpgradeChecksSuite(),
        v16p_security.V16PSecuritySuite(),
        v16p_frappe_features.V16PFrappeFeaturesSuite(),
        v16p_erpnext.V16PERPNextSuite(),
        v16p_hrms_security.V16PHRMSSecuritySuite(),
        v16p_hrms.V16PHRMSSuite(),
    ]


def suite_names() -> list[str]:
    return [s.name for s in all_suites()]
