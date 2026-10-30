"""Check that accounting assertions catch invalid or missing evidence."""

from unittest.mock import Mock

import pytest
import responses

from release_tests.client import FrappeAPIError, FrappeClient
from release_tests.suites.base import CheckFailed
from release_tests.suites.diamo_accounting import amount, ledger
from release_tests.suites.diamo_argentina_payments import DiamoHRMSPaymentsSuite
from release_tests.suites.diamo_service_credits import DiamoServiceCreditsSuite


@pytest.mark.parametrize("actual", [None, 99.99, 100.01])
def test_amount_rejects_missing_values_and_cent_differences(actual):
    with pytest.raises(CheckFailed):
        amount(actual, 100, "balance")


def test_balanced_ledger_with_wrong_accounts_is_rejected():
    client = Mock()
    client.get_list.return_value = [
        {"account": "Wrong Bank", "debit": 100, "credit": 0},
        {"account": "Debtors", "debit": 0, "credit": 100},
    ]
    with pytest.raises(CheckFailed):
        ledger(client, "TEST", {"Bank": 100, "Debtors": -100})


def test_missing_ledger_does_not_count_as_balanced():
    client = Mock()
    client.get_list.return_value = []
    with pytest.raises(AssertionError, match="missing"):
        ledger(client, "TEST", {"Bank": 100, "Debtors": -100})


@responses.activate
def test_client_retains_exception_type_independently_of_translated_message():
    responses.post(
        "https://test.example/api/resource/Sales Invoice",
        status=417,
        json={
            "exc_type": "StockOverReturnError",
            "_server_messages": "Mensaje traducido",
        },
    )
    with pytest.raises(FrappeAPIError) as caught:
        FrappeClient("https://test.example").insert({"doctype": "Sales Invoice"})
    assert caught.value.exc_type == "StockOverReturnError"


@pytest.mark.parametrize(
    "status,kind", [(403, "PermissionError"), (417, "MandatoryError"), (500, None)]
)
def test_unrelated_rejection_does_not_pass_excess_credit_check(status, kind):
    client = Mock()
    client.insert.side_effect = FrappeAPIError("unrelated failure", status=status, exc_type=kind)
    ctx = {
        "company": "Test",
        "customer": "Customer",
        "item": "Item",
        "invoice": {"name": "INV", "items": [{"name": "ROW"}]},
    }
    with pytest.raises(FrappeAPIError):
        DiamoServiceCreditsSuite().reject_excess(client, ctx)


def test_hrms_compatibility_requires_both_apps():
    suite = DiamoHRMSPaymentsSuite()
    assert not suite.applies({"erpnext": {}, "diamoerp_argentina": {}})
    assert not suite.applies({"erpnext": {}, "hrms": {}})
    assert suite.applies({"erpnext": {}, "hrms": {}, "diamoerp_argentina": {}})
