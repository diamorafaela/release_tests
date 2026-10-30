"""Prevent false positives in fiscal evidence checks."""

from unittest.mock import Mock

import pytest

from release_tests.suites.base import CheckFailed
from release_tests.suites.diamo_perceptions import DiamoPerceptionsSuite
from release_tests.suites.diamo_withholdings import DiamoWithholdingsSuite


def test_duplicate_perception_is_rejected_even_with_correct_total():
    row = {"impuesto_de_percepcion": "IVA", "account_head": "Tax", "rate": 3, "tax_amount": 30}
    ctx = {"tax": {"name": "IVA", "cuenta_de_venta": "Tax"},
           "invoice": {"docstatus": 0, "grand_total": 1030, "taxes": [row, row]}}
    with pytest.raises(AssertionError, match="exactly one"):
        DiamoPerceptionsSuite().verify(ctx, 30, 1030)


@pytest.mark.parametrize("amount", [25, 25.02, None])
def test_wrong_rounded_withholding_is_rejected(amount):
    client = Mock()
    client.call.return_value = {"ganancias": False, "iibb": {"MENDOZA": {
        "impuesto": "IIBB", "base": 1000.25, "alicuota": 2.5, "monto_retenido": amount,
    }}}
    with pytest.raises(CheckFailed):
        DiamoWithholdingsSuite().calculate(client, {"payment": {"name": "PAY"}, "tax": {"name": "IIBB"}})
