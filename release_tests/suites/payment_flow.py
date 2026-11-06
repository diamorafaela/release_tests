"""Settle invoices through the public payment mapper and the Diamo payment table."""

from decimal import Decimal

from .base import CheckFailed
from .diamo_accounting import amount, ledger


def settle_invoice(client, doctype, name):
    invoice = client.get_doc(doctype, name)
    payment = client.call(
        "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
        dt=doctype, dn=name,
    )
    payment["doctype"] = "Payment Entry"
    if "diamoerp_argentina" in client.get_versions():
        configure_diamo_payment(client, invoice, payment)
    submitted = client.submit(client.insert(payment))
    if submitted.get("docstatus") != 1:
        raise CheckFailed("payment submitted", expected="docstatus 1", actual=str(submitted.get("docstatus")))
    if "modes_of_payment" in payment:
        value = Decimal(str(invoice["outstanding_amount"]))
        ledger(client, submitted["name"], {submitted["paid_from"]: -value, submitted["paid_to"]: value})
        amount(client.get_doc(doctype, name).get("outstanding_amount"), 0, "invoice settled")
    return submitted


def configure_diamo_payment(client, invoice, payment):
    value = invoice.get("outstanding_amount")
    if value is None or Decimal(str(value)) <= 0:
        raise CheckFailed("invoice has payable debt", expected="positive outstanding", actual=str(value))
    if invoice.get("currency") != "ARS" or any(
        payment.get(field) != "ARS"
        for field in ("paid_from_account_currency", "paid_to_account_currency")
    ):
        raise CheckFailed("ARS payment fixture", expected="ARS invoice and accounts", actual=str(invoice.get("currency")))
    if payment.get("payment_type") == "Receive":
        amount(payment.get("paid_amount"), 0, "Diamo receipt mapper starts at zero")
        amount(payment.get("received_amount"), 0, "Diamo receipt mapper starts at zero")
    mode = client.get_doc("Mode of Payment", "Release Test Bank")
    banks = [row["default_account"] for row in mode["accounts"] if row["company"] == invoice["company"]]
    bank_field = "paid_to" if payment["payment_type"] == "Receive" else "paid_from"
    if banks != [payment.get(bank_field)]:
        raise CheckFailed("payment bank", expected=str(banks), actual=str(payment.get(bank_field)))
    references = payment.get("references", [])
    if len(references) != 1 or references[0].get("reference_name") != invoice["name"]:
        raise CheckFailed("payment references this invoice only", expected=invoice["name"], actual=str(references))
    references[0]["allocated_amount"] = float(value)
    payment.update(
        paid_amount=float(value), received_amount=float(value),
        reference_no=invoice["name"], reference_date=invoice["posting_date"],
        modes_of_payment=[{
            "mode_of_payment": mode["name"], "amount": float(value),
            "paid_from": payment["paid_from"], "paid_to": payment["paid_to"],
            "paid_from_account_currency": "ARS", "paid_to_account_currency": "ARS",
        }],
    )
