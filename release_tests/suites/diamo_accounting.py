"""Shared checks for Diamo's isolated accounting fixtures."""

from decimal import Decimal

from .base import CheckFailed


def amount(actual, expected, label):
    if actual is None or abs(Decimal(str(actual)) - Decimal(str(expected))) > Decimal("0.005"):
        raise CheckFailed(label, expected=str(expected), actual=str(actual))


def prepare(client, ctx):
    company = client.get_doc("Company", "Diamo Release Test")
    if company["default_currency"] != "ARS":
        raise AssertionError("Diamo Release Test must use ARS")
    ctx["company"] = company["name"]
    ctx["customer"] = client.get_doc("Customer", "Release Test Customer")["name"]
    item = client.get_doc("Item", "RT-ITEM")
    if item.get("is_stock_item") or item.get("is_fixed_asset"):
        raise AssertionError("RT-ITEM must be a non-stock service")
    ctx["item"] = item["name"]


def invoice(client, ctx):
    doc = client.insert(
        {
            "doctype": "Sales Invoice",
            "company": ctx["company"],
            "customer": ctx["customer"],
            "currency": "ARS",
            "update_stock": 0,
            "taxes": [],
            "items": [{"item_code": ctx["item"], "qty": 1, "rate": 100}],
        }
    )
    ctx["invoice"] = client.submit(doc)
    amount(ctx["invoice"].get("grand_total"), 100, "invoice total")
    amount(ctx["invoice"].get("outstanding_amount"), 100, "initial outstanding")


def ledger(client, voucher, expected):
    rows = client.get_list(
        "GL Entry",
        filters={"voucher_type": "Payment Entry", "voucher_no": voucher, "is_cancelled": 0},
        fields=["account", "debit", "credit"],
        limit=100,
    )
    if not rows or len(rows) == 100:
        raise AssertionError("missing or truncated payment ledger")
    totals = {}
    for row in rows:
        totals[row["account"]] = totals.get(row["account"], Decimal(0)) + (
            Decimal(str(row["debit"])) - Decimal(str(row["credit"]))
        )
    amount(sum(totals.values()), 0, "balanced payment ledger")
    for account, value in expected.items():
        amount(totals.pop(account, None), value, f"ledger: {account}")
    for account, value in totals.items():
        amount(value, 0, f"unexpected ledger account: {account}")
