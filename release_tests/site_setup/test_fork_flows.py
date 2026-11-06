"""Exercise release steps through Frappe's RPC functions and override resolver."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from . import QA_USER
from .fixtures import AccountingFixtures
from .identity import ensure_executor


class LocalAPIClient:
    def get_versions(self):
        return {app: {} for app in frappe.get_installed_apps()}

    def get_doc(self, doctype, name):
        return self.call("frappe.client.get", doctype=doctype, name=name)

    def get_list(self, doctype, **kwargs):
        return self.call("frappe.client.get_list", doctype=doctype,
                         limit_page_length=kwargs.pop("limit", 20), **kwargs)

    def insert(self, doc):
        return self.call("frappe.client.insert", doc=doc)

    def submit(self, doc):
        return self.call("frappe.client.submit", doc=json.dumps(doc, default=str))

    def cancel(self, doctype, name):
        return self.call("frappe.client.cancel", doctype=doctype, name=name)

    def delete(self, doctype, name):
        return self.call("frappe.client.delete", doctype=doctype, name=name)

    def call(self, method, **kwargs):
        from release_tests.client import FrappeAPIError

        if method == "rt_filter_probe":
            return {"evaluate_filters": frappe.utils.evaluate_filters(
                json.loads(kwargs["probe_doc"]), json.loads(kwargs["probe_filters"]))}
        method = frappe.override_whitelisted_method(method)
        savepoint = "rpc_" + frappe.generate_hash(length=8)
        frappe.db.savepoint(savepoint)
        try:
            result = frappe.get_attr(method)(**kwargs)
        except (frappe.PermissionError, frappe.ValidationError) as error:
            frappe.db.rollback(save_point=savepoint)
            raise FrappeAPIError(str(error), status=error.http_status_code, exc_type=type(error).__name__) from error
        return json.loads(frappe.as_json(result))


class TestForkFlows(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.enterContext(patch.dict(frappe.conf, {"developer_mode": 0}))
        self.enterContext(patch("frappe.db.commit"))
        company = "QA Fork " + frappe.generate_hash(length=8)
        abbr = "Q" + frappe.generate_hash(length=5).upper()
        self.enterContext(patch("release_tests.site_setup.COMPANY", company))
        self.enterContext(patch("release_tests.site_setup.fixtures.COMPANY", company))
        self.enterContext(patch("release_tests.site_setup.fixtures.ABBR", abbr))
        AccountingFixtures().prepare()
        with patch("diamoerp_base.overrides.user.get_limits", return_value=frappe._dict(users=1000, api_users=100)):
            self.assertEqual(ensure_executor(), [])
        frappe.set_user(QA_USER)
        self.client = LocalAPIClient()

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_generic_sales_flow_uses_argentina_payment_override(self):
        from release_tests.suites.erpnext import ERPNextSuite

        self.run_flow(ERPNextSuite())

    def test_procurement_flow_settles_non_fiscal_purchase(self):
        from release_tests.suites.erpnext_buying import ERPNextBuyingSuite

        self.run_flow(ERPNextBuyingSuite())

    def test_purchase_customizations_survive_upgrades(self):
        from release_tests.suites.diamo_purchase_contracts import DiamoPurchaseContractsSuite

        self.run_flow(DiamoPurchaseContractsSuite())

    def test_shipped_fields_and_administrative_boundaries(self):
        from release_tests.suites.diamo_customizations import DiamoCustomizationsSuite

        self.run_flow(DiamoCustomizationsSuite())

    def test_effective_controller_and_rpc_override_chains(self):
        from .contracts import check_runtime_contracts

        self.assertEqual(check_runtime_contracts(), [])
        with patch("frappe.override_whitelisted_method", side_effect=lambda method: method):
            self.assertTrue(any("RPC override changed" in error for error in check_runtime_contracts()))

    def test_supported_frappe_range_contract(self):
        from release_tests.suites.diamo_frappe_filters import DiamoFrappeFiltersSuite

        self.run_flow(DiamoFrappeFiltersSuite())

    def test_manufacturing_flow_as_qa(self):
        from release_tests.suites.erpnext_manufacturing import ERPNextManufacturingSuite

        self.run_flow(ERPNextManufacturingSuite())

    def test_distribution_flow_as_qa(self):
        from release_tests.suites.erpnext_selling import ERPNextSellingSuite

        self.run_flow(ERPNextSellingSuite())

    def test_service_flow_as_qa(self):
        from release_tests.suites.erpnext_service import ERPNextServiceSuite

        self.run_flow(ERPNextServiceSuite())

    def run_flow(self, suite):
        context = {}
        for step in suite.build_steps(self.client.get_versions()):
            step.fn(self.client, context)
