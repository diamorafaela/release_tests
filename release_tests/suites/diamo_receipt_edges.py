"""Cent-accurate partial receipts and cancellation of an earlier allocation."""

from decimal import Decimal

from . import diamo_accounting as checks
from .payment_flow import configure_diamo_payment


def partial_receipts(client, ctx):
    ctx["partial_receipts"] = []
    for value, remaining in (("33.33", "66.67"), ("33.33", "33.34"), ("33.34", "0")):
        payment = receive(client, ctx, value)
        ctx["partial_receipts"].append(payment)
        outstanding(client, ctx, remaining)


def reverse_receipts(client, ctx):
    # Cancel in original order: later allocations must remain valid.
    for payment, remaining in zip(ctx["partial_receipts"], ("33.33", "66.66", "100"), strict=True):
        cancel(client, payment)
        outstanding(client, ctx, remaining)
    payment = receive(client, ctx, "100")
    outstanding(client, ctx, 0)
    cancel(client, payment)
    outstanding(client, ctx, 100)


def multiple_invoices(client, ctx):
    first, second = dict(ctx), dict(ctx)
    checks.invoice(client, first)
    checks.invoice(client, second)
    payments = []
    for context in (first, second):
        invoice = context["invoice"]
        payment = client.call(
            "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
            dt="Sales Invoice", dn=invoice["name"],
        )
        configure_diamo_payment(client, invoice, payment)
        payments.append(payment)
    payment = payments[0]
    payment["references"].extend(payments[1]["references"])
    payment.update(doctype="Payment Entry", paid_amount=200, received_amount=200)
    payment["modes_of_payment"][0]["amount"] = 200
    submitted = client.submit(client.insert(payment))
    if submitted.get("docstatus") != 1:
        raise AssertionError("multi-invoice receipt must be submitted")
    references = submitted.get("references", [])
    if len(references) != 2 or {row["reference_name"] for row in references} != {
        first["invoice"]["name"], second["invoice"]["name"],
    }:
        raise AssertionError("receipt must preserve both invoice references")
    for row in references:
        checks.amount(row.get("allocated_amount"), 100, "per-invoice allocation")
    checks.amount(submitted.get("unallocated_amount"), 0, "multi-invoice unallocated amount")
    checks.ledger(client, submitted["name"], {submitted["paid_to"]: 200, submitted["paid_from"]: -200})
    for context in (first, second):
        outstanding(client, context, 0)
    cancel(client, submitted)
    for context in (first, second):
        outstanding(client, context, 100)


def receive(client, ctx, value):
    invoice = client.get_doc("Sales Invoice", ctx["invoice"]["name"])
    payment = client.call(
        "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
        dt="Sales Invoice", dn=invoice["name"],
    )
    configure_diamo_payment(client, invoice, payment)
    payment.update(doctype="Payment Entry", paid_amount=float(value), received_amount=float(value))
    payment["references"][0]["allocated_amount"] = float(value)
    payment["modes_of_payment"][0]["amount"] = float(value)
    submitted = client.submit(client.insert(payment))
    if submitted.get("docstatus") != 1:
        raise AssertionError("partial receipt must be submitted")
    checks.amount(submitted.get("total_allocated_amount"), value, "allocated receipt")
    checks.amount(submitted.get("unallocated_amount"), 0, "no unallocated receipt")
    checks.ledger(client, submitted["name"], {
        submitted["paid_to"]: Decimal(value), submitted["paid_from"]: -Decimal(value),
    })
    return submitted


def outstanding(client, ctx, expected):
    invoice = client.get_doc("Sales Invoice", ctx["invoice"]["name"])
    checks.amount(invoice.get("outstanding_amount"), expected, "partial receipt invoice balance")


def cancel(client, payment):
    cancelled = client.cancel("Payment Entry", payment["name"])
    if cancelled.get("docstatus") != 2:
        raise AssertionError("partial receipt must be cancelled")
    active = client.get_list("GL Entry", filters={
        "voucher_type": "Payment Entry", "voucher_no": payment["name"], "is_cancelled": 0,
    }, limit=1)
    if active:
        raise AssertionError("cancelled partial receipt retains active ledger entries")
