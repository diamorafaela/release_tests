"""Negative checks must fail closed without leaking test account credentials."""

import json
from unittest.mock import Mock

import pytest

from release_tests.client import FrappeAPIError, FrappeClient
from release_tests.suites.base import CheckFailed
from release_tests.suites.diamo_base_access import (
    DiamoBaseAccessSuite,
    expect_rejection,
    isolated_client,
    temporary_user,
)


@pytest.mark.parametrize(
    "status,kind", [(500, "PermissionError"), (401, "AuthenticationError"), (403, None)]
)
def test_permissions_check_rejects_unrelated_errors(status, kind):
    action = Mock(side_effect=FrappeAPIError("failure", status=status, exc_type=kind))
    with pytest.raises(FrappeAPIError):
        expect_rejection(action, 403, "PermissionError")


def test_permissions_check_rejects_success():
    with pytest.raises(AssertionError, match="operation succeeded"):
        expect_rejection(lambda: [], 403, "PermissionError")


def test_temporary_user_is_disabled_when_check_fails():
    client = Mock()
    client.get_doc.return_value = {"doctype": "User", "enabled": 1}
    with pytest.raises(AssertionError, match="regression"):
        with temporary_user(client, api=True):
            raise AssertionError("regression")
    saved = json.loads(client.call.call_args.kwargs["doc"])
    assert saved["enabled"] == 0
    assert "new_password" not in saved
    assert "api_secret" not in saved


def test_failed_user_creation_does_not_disable_an_existing_user():
    client = Mock()
    client.insert.side_effect = FrappeAPIError("quota exhausted", status=417)
    with pytest.raises(FrappeAPIError):
        with temporary_user(client, api=True):
            pytest.fail("creation must fail")
    client.get_doc.assert_not_called()
    client.call.assert_not_called()


def test_secondary_identity_never_inherits_admin_authentication():
    parent = FrappeClient("http://127.0.0.1:8001", host_header="test.localhost")
    parent.use_token("admin-key", "admin-secret")
    parent.session.cookies.set("sid", "admin-session")
    with isolated_client(parent) as secondary:
        assert secondary.session.headers["Host"] == "test.localhost"
        assert "Authorization" not in secondary.session.headers
        assert not secondary.session.cookies


@pytest.mark.parametrize("field", ["grand_total", "base_grand_total", "outstanding_amount"])
def test_denied_document_read_does_not_hide_financial_list_leak(field):
    admin, reduced = Mock(), Mock()
    admin.insert.return_value = {"name": "TEST-INVOICE"}
    reduced.get_doc.side_effect = FrappeAPIError("denied", status=403, exc_type="PermissionError")
    reduced.get_list.side_effect = [[{"name": "TEST-INVOICE"}], [{"name": "TEST-INVOICE", field: 100}]]
    reduced.logged_in_user = "reduced@example.com"
    with pytest.raises(CheckFailed) as failure:
        DiamoBaseAccessSuite().reject_invoice_access(admin, reduced, "Test Customer")
    assert failure.value.details["actual"] == f"exposed fields: ['{field}']"
    admin.delete.assert_called_once_with("Sales Invoice", "TEST-INVOICE")


def test_rejected_financial_projection_preserves_link_access():
    admin, reduced = Mock(), Mock()
    denied = FrappeAPIError("denied", status=403, exc_type="PermissionError")
    admin.insert.return_value = {"name": "TEST-INVOICE"}
    reduced.get_doc.side_effect = denied
    reduced.get_list.side_effect = [[{"name": "TEST-INVOICE"}], denied]
    DiamoBaseAccessSuite().reject_invoice_access(admin, reduced, "Test Customer")
    admin.delete.assert_called_once_with("Sales Invoice", "TEST-INVOICE")
