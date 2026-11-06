from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from . import QA_USER, check, prepare
from .fixtures import AccountingFixtures, ensure, ensure_leaf_group


class TestSiteSetup(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.enterContext(patch("frappe.db.commit"))
        self.previous_developer_mode = frappe.conf.developer_mode
        frappe.conf.developer_mode = 0

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.conf.developer_mode = self.previous_developer_mode
        super().tearDown()

    def test_fresh_accounting_company_is_repeatable(self):
        name = "QA Setup " + frappe.generate_hash(length=8)
        abbr = "Q" + frappe.generate_hash(length=5).upper()
        with patch("release_tests.site_setup.fixtures.COMPANY", name), patch(
            "release_tests.site_setup.fixtures.ABBR", abbr
        ):
            AccountingFixtures().prepare()
            accounts = frappe.db.count("Account", {"company": name})
            AccountingFixtures().prepare()
        self.assertEqual(frappe.db.count("Account", {"company": name}), accounts)
        self.assertEqual(frappe.db.get_value("Company", name, "default_currency"), "ARS")
        company = frappe.get_doc("Company", name)
        for field in ("default_inventory_account", "stock_received_but_not_billed", "stock_adjustment_account"):
            account = frappe.get_doc("Account", company.get(field))
            self.assertEqual(account.company, name)
            self.assertFalse(account.is_group)
        for kind in ("Bank", "Cash"):
            payment = frappe.get_doc("Mode of Payment", f"Release Test {kind}")
            self.assertEqual(len([row for row in payment.accounts if row.company == name]), 1)

    def test_fixture_conflict_does_not_overwrite_existing_data(self):
        name = "QA Role " + frappe.generate_hash(length=8)
        ensure("Role", name, {"role_name": name, "desk_access": 1})
        with self.assertRaises(frappe.ValidationError):
            ensure("Role", name, {"desk_access": 0}, verify=("desk_access",))
        self.assertEqual(frappe.db.get_value("Role", name, "desk_access"), 1)

    def test_filter_runs_are_isolated_without_deleting_other_runs(self):
        from release_tests.suites.frappe_filters import _between_on_date, _seed

        class LocalClient:
            def insert(self, values):
                return frappe.get_doc(values).insert().as_dict()

            def get_list(self, doctype, **kwargs):
                return frappe.get_list(doctype, **kwargs)

        client = LocalClient()
        first, second = {}, {}
        _seed(client, first)
        _seed(client, second)
        _between_on_date(client, first)
        _between_on_date(client, second)
        self.assertNotEqual(first["filter_marker"], second["filter_marker"])
        self.assertTrue(frappe.db.exists("ToDo", first["todos"]["d1"]))

    def test_fiscal_fixtures_can_be_created_and_repeated(self):
        fixtures = (
            ("Customer", "Release Test Customer"),
            ("Supplier", "Release Test Supplier"),
            ("Item", "RT-ITEM"),
            ("Customer Group", "Release Test Customer Group"),
            ("Supplier Group", "Release Test Supplier Group"),
            ("Item Group", "Release Test Item Group"),
            ("Impuesto de Percepcion", "Release Test IVA 3%"),
            ("Impuesto de Retencion", "Release Test IIBB 2.5%"),
            ("Customer", "Release Test Fiscal Customer"),
            ("Supplier", "Release Test Fiscal Supplier"),
            ("Punto de Venta", "Release Test Manual"),
        )
        # The integration transaction restores any existing fixture records after the test.
        for dt, name in fixtures:
            for field in frappe.get_meta(dt).get_table_fields():
                frappe.db.delete(field.options, {"parent": name, "parenttype": dt})
            frappe.db.delete(dt, {"name": name})
            frappe.clear_document_cache(dt, name)
        name = "QA Fiscal " + frappe.generate_hash(length=8)
        abbr = "Q" + frappe.generate_hash(length=5).upper()
        with patch("release_tests.site_setup.fixtures.COMPANY", name), patch(
            "release_tests.site_setup.fixtures.ABBR", abbr
        ), patch("release_tests.site_setup.fiscal.COMPANY", name):
            AccountingFixtures().prepare(fiscal=True)
            AccountingFixtures().prepare(fiscal=True)
        self.assertEqual(frappe.db.get_value("Impuesto de Retencion", "Release Test IIBB 2.5%", "company"), name)
        pos = frappe.get_doc("Punto de Venta", "Release Test Manual")
        self.assertEqual(pos.habilitado, 1)
        self.assertEqual(len(pos.secuencias), 1)
        for doctype, master in (
            ("Customer", "Release Test Customer"), ("Customer", "Release Test Fiscal Customer"),
            ("Supplier", "Release Test Supplier"), ("Supplier", "Release Test Fiscal Supplier"),
            ("Item", "RT-ITEM"),
        ):
            group = frappe.db.get_value(doctype, master, f"{doctype.lower()}_group")
            self.assertEqual(group, f"Release Test {doctype} Group")
            self.assertEqual(frappe.db.get_value(f"{doctype} Group", group, "is_group"), 0)

    def test_existing_qa_group_must_be_a_leaf(self):
        name = ensure_leaf_group("Customer")
        frappe.db.set_value("Customer Group", name, "is_group", 1)
        with self.assertRaisesRegex(frappe.ValidationError, "Fixture conflict"):
            ensure_leaf_group("Customer")
        self.assertEqual(frappe.db.get_value("Customer Group", name, "is_group"), 1)

    def test_non_administrator_cannot_prepare_or_check(self):
        frappe.set_user("Guest")
        for method in (prepare, check):
            with self.assertRaises(frappe.PermissionError):
                method(suites=["core_frappe"])

    def test_preflight_is_read_only_and_reports_missing_identity(self):
        with patch("frappe.db.sql", wraps=frappe.db.sql) as sql:
            result = check(suites=["core_frappe"], user="missing-qa@example.com")
        self.assertFalse(result["ready"])
        self.assertTrue(any("Missing User" in value for value in result["blockers"]))
        for call in sql.call_args_list:
            query = str(call.args[0]).lstrip().lower()
            self.assertFalse(query.startswith(("insert ", "update ", "delete ", "alter ")))

    def test_preflight_does_not_claim_unsupported_suites_are_ready(self):
        result = check(suites=["v16p_security"], user="Administrator")
        self.assertFalse(result["ready"])
        self.assertTrue(any("not yet covered" in value for value in result["blockers"]))

    def test_preflight_reports_base_administrator_only_restrictions(self):
        result = check(suites=["customisations"], user="integracion@diamo.com.ar")
        self.assertTrue(any("restricted to Administrator" in value for value in result["blockers"]))

    def test_executor_preparation_preserves_credentials(self):
        from diamoerp_base.overrides.user import generate_keys

        from .identity import ensure_executor

        with patch("diamoerp_base.overrides.user.get_limits", return_value=frappe._dict(users=1000, api_users=100)):
            self.assertEqual(ensure_executor(), [])
            credentials = generate_keys(QA_USER)
            self.assertEqual(ensure_executor(), [])
            self.assertEqual(ensure_executor(), [])
        user = frappe.get_doc("User", QA_USER)
        self.assertEqual(user.api_key, credentials["api_key"])
        self.assertEqual(user.get_password("api_secret"), credentials["api_secret"])
        self.assertEqual(len(user.roles), len({row.role for row in user.roles}))

    def test_curated_profile_is_repeatable_and_preserves_operator_edits(self):
        from release_tests.profiles import install_diamo

        if not frappe.db.exists("DocType", "Test Case Group"):
            self.skipTest("Release Manager is not installed")
        first = install_diamo()
        self.assertEqual(install_diamo(), first)
        group = frappe.get_doc("Test Case Group", first["profile"])
        group.remove(group.test_cases[-1])
        group.save()
        with self.assertRaisesRegex(frappe.ValidationError, "differs from the shipped profile"):
            install_diamo()
        group.reload()
        self.assertEqual(len(group.test_cases), len(first["suites"]) - 1)
