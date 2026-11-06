from unittest.mock import Mock

import pytest

from release_tests.diamo_contracts import CORE_SUITES
from release_tests.site_setup import select_suites
from release_tests.suites.base import CheckFailed
from release_tests.suites.diamo_customizations import DiamoCustomizationsSuite
from release_tests.suites.diamo_frappe_filters import DiamoFrappeFiltersSuite
from release_tests.suites.payment_flow import configure_diamo_payment


def payment_fixture():
    invoice = {"name": "INV", "company": "QA", "posting_date": "2026-11-06",
               "currency": "ARS", "outstanding_amount": 100.01}
    payment = {"payment_type": "Receive", "paid_amount": 0, "received_amount": 0,
               "paid_from": "Debtors", "paid_to": "Bank", "paid_from_account_currency": "ARS",
               "paid_to_account_currency": "ARS", "references": [{"reference_name": "INV"}]}
    client = Mock()
    client.get_doc.return_value = {"name": "Release Test Bank", "accounts": [
        {"company": "QA", "default_account": "Bank"}]}
    return client, invoice, payment


@pytest.mark.parametrize("change", [
    {"paid_amount": 100.01}, {"received_amount": 100.01},
    {"paid_to_account_currency": "USD"}, {"paid_to": "Other bank"},
    {"references": [{"reference_name": "OTHER"}]},
])
def test_payment_adapter_does_not_hide_broken_mapper_contracts(change):
    client, invoice, payment = payment_fixture()
    payment.update(change)
    with pytest.raises(CheckFailed):
        configure_diamo_payment(client, invoice, payment)


def test_payment_adapter_preserves_cents_and_allocates_actual_debt():
    client, invoice, payment = payment_fixture()
    configure_diamo_payment(client, invoice, payment)
    assert payment["modes_of_payment"][0]["amount"] == 100.01
    assert payment["references"][0]["allocated_amount"] == 100.01


def test_missing_shipped_custom_field_is_a_regression():
    client = Mock()
    client.call.return_value = []
    with pytest.raises(CheckFailed, match="User.enable_api_access"):
        DiamoCustomizationsSuite().fields(client, {})


def test_python_range_disagreement_remains_a_failure():
    client = Mock()
    client.call.return_value = {"evaluate_filters": False}
    ctx = {"todos": {"d1": "A", "d2": "B", "d3": "C"}, "db_result": {"A", "B"}}
    with pytest.raises(CheckFailed):
        DiamoFrappeFiltersSuite().python_range(client, ctx)


def test_curated_profile_is_registered_and_keeps_diamo_regressions():
    assert select_suites("diamo") == select_suites(list(CORE_SUITES))
    assert {"diamo_base_access", "diamo_purchase_contracts", "diamo_customizations"} <= set(CORE_SUITES)
    assert not any(suite.startswith("v16p_") for suite in CORE_SUITES)
