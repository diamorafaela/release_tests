"""Execute the fiscal release suites through real RPCs under the QA user."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from . import QA_USER
from .fixtures import AccountingFixtures
from .identity import ensure_executor
from .test_fork_flows import LocalAPIClient


class TestFiscalEdges(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.enterContext(patch("frappe.db.commit"))
        self.enterContext(patch.dict(frappe.conf, {"developer_mode": 0}))
        frappe.db.delete("Item Price", {"item_code": "RT-ITEM"})
        # Recreate deterministic masters inside the rollback-only test transaction.
        for doctype, name in (
            ("Customer", "Release Test Customer"), ("Supplier", "Release Test Supplier"),
            ("Item", "RT-ITEM"), ("Customer", "Release Test Fiscal Customer"),
            ("Supplier", "Release Test Fiscal Supplier"), ("Punto de Venta", "Release Test Manual"),
            ("Impuesto de Percepcion", "Release Test IVA 3%"),
            ("Impuesto de Retencion", "Release Test IIBB 2.5%"),
        ):
            for field in frappe.get_meta(doctype).get_table_fields():
                frappe.db.delete(field.options, {"parent": name, "parenttype": doctype})
            frappe.db.delete(doctype, {"name": name})
            frappe.clear_document_cache(doctype, name)
        AccountingFixtures().prepare(fiscal=True)
        with patch("diamoerp_base.overrides.user.get_limits", return_value=frappe._dict(users=1000, api_users=100)):
            self.assertEqual(ensure_executor(), [])
        frappe.set_user(QA_USER)

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_perception_boundaries_rounding_and_recalculation(self):
        from release_tests.suites.diamo_perceptions import DiamoPerceptionsSuite

        suite, client, context = DiamoPerceptionsSuite(), LocalAPIClient(), {}
        suite.prepare(client, context)
        suite.minimum_boundary(client, context)
        suite.fractional_tax(client, context)

    def test_existing_perception_is_removed_below_minimum(self):
        from release_tests.suites.diamo_perceptions import DiamoPerceptionsSuite

        suite, client, context = DiamoPerceptionsSuite(), LocalAPIClient(), {}
        suite.prepare(client, context)
        suite.cross_minimum(client, context)

    def test_withholding_boundaries_preview_and_reversal(self):
        from release_tests.suites.diamo_withholdings import DiamoWithholdingsSuite

        self.run_suite(DiamoWithholdingsSuite())

    def run_suite(self, suite):
        client, context = LocalAPIClient(), {}
        for step in suite.build_steps(client.get_versions()):
            step.fn(client, context)
