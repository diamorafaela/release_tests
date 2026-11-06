"""Idempotent get-or-create helpers shared across suites.

Every helper queries by a deterministic name first and only inserts when the
record is missing, so re-running the harness against the same site is safe and
never piles up duplicate master data.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from .client import FrappeClient


def _json(value: Any) -> str:
    return json.dumps(value, default=str)

# Deterministic names so re-runs are idempotent and easy to spot/clean up.
RT_COMPANY = "Release Test Co"
RT_COMPANY_ABBR = "RTC"
RT_CUSTOMER = "Release Test Customer"
RT_ITEM = "RT-ITEM"
RT_STOCK_ITEM = "RT-STOCK-ITEM"
RT_SERIAL_ITEM = "RT-SERIAL-ITEM"
RT_BATCH_ITEM = "RT-BATCH-ITEM"
RT_SERVICE_ITEM = "RT-SERVICE-ITEM"
RT_FG_ITEM = "RT-FG-ITEM"
RT_RAW_ITEM = "RT-RAW-ITEM"
RT_WAREHOUSE = "Release Warehouse"
RT_SUPPLIER = "Release Test Supplier"
RT_EMPLOYEE = "Release Test Employee"
RT_EMPLOYEE_2 = "Release Report Employee"
RT_LEAVE_TYPE = "Release Leave Type"
RT_EXPENSE_TYPE = "Release Expense Type"


def _get_or_create(client: FrappeClient, doctype: str, name: str, doc: dict[str, Any]) -> str:
    """Return the name of an existing doc, else insert ``doc`` and return its name."""
    existing = client.get_list(doctype, filters={"name": name}, fields=["name"], limit=1)
    if existing:
        return existing[0]["name"]
    created = client.insert({"doctype": doctype, **doc})
    return created["name"]


def _hsn_code(client: FrappeClient) -> str | None:
    """A valid HSN/SAC code, if India Compliance's master is present.

    India Compliance makes ``gst_hsn_code`` mandatory on Items; we borrow the
    first code from its master. Returns None on sites without the app so item
    creation stays generic.
    """
    # India Compliance requires the code to be exactly 6 or 8 digits; the master
    # also holds shorter chapter headings, so match an 8-char name via LIKE.
    try:
        codes = client.get_list(
            "GST HSN Code", filters={"name": ["like", "________"]}, fields=["name"], limit=1
        )
    except Exception:  # noqa: BLE001 - doctype absent when the app isn't installed
        return None
    return codes[0]["name"] if codes else None


def ensure_company(client: FrappeClient) -> str:
    from .site_setup import COMPANY

    prepared = client.get_list("Company", filters={"name": COMPANY}, fields=["name"], limit=1)
    if prepared:
        return prepared[0]["name"]
    existing = client.get_list("Company", fields=["name"], limit=1)
    if existing:
        # Prefer whatever company the site already has — fresh sites have one
        # from the setup wizard; we only create our own if none exists.
        return existing[0]["name"]
    return _get_or_create(
        client,
        "Company",
        RT_COMPANY,
        {
            "company_name": RT_COMPANY,
            "abbr": RT_COMPANY_ABBR,
            "default_currency": "INR",
            "country": "India",
        },
    )


def ensure_customer(client: FrappeClient) -> str:
    return _get_or_create(
        client,
        "Customer",
        RT_CUSTOMER,
        {"customer_name": RT_CUSTOMER, "customer_type": "Company"},
    )


def ensure_item(client: FrappeClient) -> str:
    doc = {
        "item_code": RT_ITEM,
        "item_name": "Release Test Item",
        "is_stock_item": 0,
        "stock_uom": "Nos",
        "item_group": "All Item Groups",
    }
    hsn = _hsn_code(client)
    if hsn:
        doc["gst_hsn_code"] = hsn
    return _get_or_create(client, "Item", RT_ITEM, doc)


def ensure_employee(client: FrappeClient, company: str) -> str:
    return _ensure_employee(client, company, RT_EMPLOYEE)


def ensure_employee2(client: FrappeClient, company: str, reports_to: str) -> str:
    """A second Employee that reports to ``reports_to`` (the manager)."""
    return _ensure_employee(client, company, RT_EMPLOYEE_2, reports_to)


def _ensure_employee(
    client: FrappeClient,
    company: str,
    first_name: str,
    reports_to: str | None = None,
) -> str:
    # Key on first_name: HRMS overwrites employee_name from the name parts, so a
    # get-or-create on employee_name never matches. order_by keeps it stable.
    existing = client.get_list(
        "Employee",
        filters={"first_name": first_name},
        fields=["name"],
        order_by="creation asc",
        limit=1,
    )
    if existing:
        return existing[0]["name"]
    doc = {
        "doctype": "Employee",
        "first_name": first_name,
        "company": company,
        "gender": "Other",
        "date_of_joining": "2020-01-01",
        "date_of_birth": "1990-01-01",
        "status": "Active",
    }
    if reports_to:
        doc["reports_to"] = reports_to
    return client.insert(doc)["name"]


# ------------------------------------------------------------------- stock
def ensure_warehouse(client: FrappeClient, company: str) -> str:
    # ERPNext suffixes warehouse names with the company abbreviation.
    abbr = client.get_list("Company", filters={"name": company}, fields=["abbr"], limit=1)[0]["abbr"]
    name = f"{RT_WAREHOUSE} - {abbr}"
    existing = client.get_list("Warehouse", filters={"name": name}, fields=["name"], limit=1)
    if existing:
        return existing[0]["name"]
    return client.insert(
        {"doctype": "Warehouse", "warehouse_name": RT_WAREHOUSE, "company": company}
    )["name"]


def ensure_stock_item(client: FrappeClient, company: str, warehouse: str) -> str:
    existing = client.get_list("Item", filters={"name": RT_STOCK_ITEM}, fields=["name"], limit=1)
    if existing:
        return existing[0]["name"]
    doc = {
        "doctype": "Item",
        "item_code": RT_STOCK_ITEM,
        "item_name": "Release Stock Item",
        "is_stock_item": 1,
        "stock_uom": "Nos",
        "item_group": "All Item Groups",
        "item_defaults": [{"company": company, "default_warehouse": warehouse}],
    }
    hsn = _hsn_code(client)
    if hsn:
        doc["gst_hsn_code"] = hsn
    return client.insert(doc)["name"]


def ensure_supplier(client: FrappeClient) -> str:
    return _get_or_create(
        client,
        "Supplier",
        RT_SUPPLIER,
        {"supplier_name": RT_SUPPLIER, "supplier_group": "All Supplier Groups"},
    )


def ensure_stock_on_hand(
    client: FrappeClient, company: str, item: str, warehouse: str, qty: float, rate: float = 100
) -> None:
    """Top up stock via a Material Receipt only if the Bin is short of ``qty``."""
    bins = client.get_list(
        "Bin", filters={"item_code": item, "warehouse": warehouse}, fields=["actual_qty"], limit=1
    )
    on_hand = float(bins[0]["actual_qty"]) if bins else 0.0
    if on_hand >= qty:
        return
    receipt = {
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Receipt",
        "company": company,
        "items": [
            {"item_code": item, "qty": qty - on_hand, "basic_rate": rate, "t_warehouse": warehouse}
        ],
    }
    client.submit({**client.insert(receipt)})


# -------------------------------------------------------------------- leave
def ensure_leave_type(client: FrappeClient) -> str:
    return _get_or_create(
        client,
        "Leave Type",
        RT_LEAVE_TYPE,
        {"leave_type_name": RT_LEAVE_TYPE, "max_leaves_allowed": 20},
    )


def ensure_holiday_list(client: FrappeClient, employee: str) -> str:
    """Ensure a current-year Holiday List is assigned to the employee.

    HRMS v16 resolves an employee's holidays through a submittable "Holiday List
    Assignment" record (the ``Employee.holiday_list`` field is no longer consulted
    for leave-day calculation), so we create + submit one if the employee has none.
    """
    from datetime import date

    year = date.today().year
    name = f"Release Holiday List {year}"
    existing = client.get_list("Holiday List", filters={"name": name}, fields=["name"], limit=1)
    holiday_list = (
        existing[0]["name"]
        if existing
        else client.insert(
            {
                "doctype": "Holiday List",
                "holiday_list_name": name,
                "from_date": f"{year}-01-01",
                "to_date": f"{year}-12-31",
            }
        )["name"]
    )
    assigned = client.get_list(
        "Holiday List Assignment",
        filters={"assigned_to": employee, "docstatus": 1},
        fields=["name"],
        limit=1,
    )
    if not assigned:
        client.submit(
            {
                **client.insert(
                    {
                        "doctype": "Holiday List Assignment",
                        "applicable_for": "Employee",
                        "assigned_to": employee,
                        "holiday_list": holiday_list,
                        "from_date": f"{year}-01-01",
                    }
                )
            }
        )
    return holiday_list


def ensure_leave_period(client: FrappeClient, company: str) -> str:
    """A Leave Period spanning the current calendar year."""
    from datetime import date

    year = date.today().year
    from_date, to_date = f"{year}-01-01", f"{year}-12-31"
    existing = client.get_list(
        "Leave Period",
        filters={"from_date": from_date, "to_date": to_date, "company": company},
        fields=["name"],
        limit=1,
    )
    if existing:
        return existing[0]["name"]
    return client.insert(
        {
            "doctype": "Leave Period",
            "from_date": from_date,
            "to_date": to_date,
            "company": company,
            "is_active": 1,
        }
    )["name"]


# ------------------------------------------------------- item types + mfg
def _company_currency(client: FrappeClient, company: str) -> str:
    row = client.get_list("Company", filters={"name": company}, fields=["default_currency"], limit=1)
    return (row and row[0].get("default_currency")) or "INR"


def _new_item(client: FrappeClient, code: str, name: str, extra: dict[str, Any]) -> str:
    existing = client.get_list("Item", filters={"name": code}, fields=["name"], limit=1)
    if existing:
        return existing[0]["name"]
    doc = {
        "doctype": "Item",
        "item_code": code,
        "item_name": name,
        "item_group": "All Item Groups",
        "stock_uom": "Nos",
        **extra,
    }
    hsn = _hsn_code(client)
    if hsn:
        doc["gst_hsn_code"] = hsn
    return client.insert(doc)["name"]


def ensure_serialised_item(client: FrappeClient, company: str, warehouse: str) -> str:
    return _new_item(
        client,
        RT_SERIAL_ITEM,
        "Release Serial Item",
        {
            "is_stock_item": 1,
            "has_serial_no": 1,
            "serial_no_series": "RT-SER-.#####",
            "item_defaults": [{"company": company, "default_warehouse": warehouse}],
        },
    )


def ensure_batched_item(client: FrappeClient, company: str, warehouse: str) -> str:
    return _new_item(
        client,
        RT_BATCH_ITEM,
        "Release Batch Item",
        {
            "is_stock_item": 1,
            "has_batch_no": 1,
            "create_new_batch": 1,
            "batch_number_series": "RT-BATCH-.#####",
            "item_defaults": [{"company": company, "default_warehouse": warehouse}],
        },
    )


def ensure_service_item(client: FrappeClient) -> str:
    return _new_item(client, RT_SERVICE_ITEM, "Release Service Item", {"is_stock_item": 0})


def ensure_serial_batch_enabled(client: FrappeClient) -> None:
    """Turn on Stock Settings' master serial/batch toggle if it's off (site-wide)."""
    settings = client.get_doc("Stock Settings", "Stock Settings")
    if not settings.get("enable_serial_and_batch_no_for_item"):
        client.call(
            "frappe.client.set_value",
            doctype="Stock Settings",
            name="Stock Settings",
            fieldname="enable_serial_and_batch_no_for_item",
            value=1,
        )


def ensure_named_warehouse(client: FrappeClient, company: str, base_name: str) -> str:
    abbr = client.get_list("Company", filters={"name": company}, fields=["abbr"], limit=1)[0]["abbr"]
    name = f"{base_name} - {abbr}"
    existing = client.get_list("Warehouse", filters={"name": name}, fields=["name"], limit=1)
    if existing:
        return existing[0]["name"]
    return client.insert(
        {"doctype": "Warehouse", "warehouse_name": base_name, "company": company}
    )["name"]


def ensure_fg_item(client: FrappeClient, company: str, warehouse: str) -> str:
    return _new_item(
        client,
        RT_FG_ITEM,
        "Release Finished Good",
        {"is_stock_item": 1, "item_defaults": [{"company": company, "default_warehouse": warehouse}]},
    )


def ensure_raw_item(client: FrappeClient, company: str, warehouse: str) -> str:
    return _new_item(
        client,
        RT_RAW_ITEM,
        "Release Raw Material",
        {"is_stock_item": 1, "item_defaults": [{"company": company, "default_warehouse": warehouse}]},
    )


def ensure_manufacturing_warehouses(client: FrappeClient, company: str) -> dict[str, str]:
    return {
        "source": ensure_named_warehouse(client, company, "Release Source WH"),
        "wip": ensure_named_warehouse(client, company, "Release WIP WH"),
        "fg": ensure_named_warehouse(client, company, "Release FG WH"),
    }


def ensure_bom(client: FrappeClient, company: str, fg_item: str, raw_items: list[tuple]) -> str:
    """Get-or-create a submitted, active BOM. ``raw_items`` = [(item_code, qty, rate), ...]."""
    existing = client.get_list(
        "BOM",
        filters={"item": fg_item, "is_active": 1, "docstatus": 1},
        fields=["name"],
        limit=1,
    )
    if existing:
        return existing[0]["name"]
    doc = {
        "doctype": "BOM",
        "item": fg_item,
        "quantity": 1,
        "company": company,
        "currency": _company_currency(client, company),
        "conversion_rate": 1,
        "with_operations": 0,
        "is_active": 1,
        "is_default": 1,
        "items": [
            {"item_code": code, "qty": qty, "uom": "Nos", "rate": rate}
            for code, qty, rate in raw_items
        ],
    }
    return client.submit({**client.insert(doc)})["name"]


def ensure_expense_claim_type(client: FrappeClient) -> str:
    return _get_or_create(
        client,
        "Expense Claim Type",
        RT_EXPENSE_TYPE,
        {"expense_type": RT_EXPENSE_TYPE},
    )


# ------------------------------------------------------- India Compliance (GST)
# IC's own test GSTINs (pass its validation). Company + customer in different
# states so the invoice is inter-state -> IGST.
RT_COMPANY_GSTIN = "24AAQCA8719H1ZC"  # Gujarat (state 24)
RT_CUSTOMER_GSTIN = "27AAQCA8719H1Z6"  # Maharashtra (27)
RT_GST_CUSTOMER = "Release GST Customer"
RT_GST_ITEMS = [
    ("RT-GST-5", "Release GST Item 5%", 5),
    ("RT-GST-12", "Release GST Item 12%", 12),
    ("RT-GST-18", "Release GST Item 18%", 18),
]


def ensure_gst_company(client: FrappeClient) -> str:
    """Ensure the site company carries a (test) GSTIN + Registered Regular category."""
    company = ensure_company(client)
    row = client.get_list("Company", filters={"name": company}, fields=["gstin"], limit=1)[0]
    if not row.get("gstin"):
        client.call(
            "frappe.client.set_value",
            doctype="Company",
            name=company,
            fieldname={"gstin": RT_COMPANY_GSTIN, "gst_category": "Registered Regular"},
        )
    return company


def output_igst_account(client: FrappeClient, company: str) -> str | None:
    """The company's Output IGST account, from GST Settings (IC auto-creates it)."""
    settings = client.get_doc("GST Settings", "GST Settings")
    for r in settings.get("gst_accounts", []):
        if r.get("account_type") == "Output" and r.get("company") == company:
            return r.get("igst_account")
    return None


def ensure_company_gst_address(client: FrappeClient, company: str) -> str:
    """A company Address carrying the GSTIN — IC needs it to stamp company_gstin."""
    existing = client.get_list("Address", filters={"gstin": RT_COMPANY_GSTIN}, fields=["name"], limit=1)
    if existing:
        return existing[0]["name"]
    doc = {
        "doctype": "Address",
        "address_title": "Release Test Co GST",
        "address_type": "Billing",
        "address_line1": "1 Test Road",
        "city": "Ahmedabad",
        "state": "Gujarat",
        "country": "India",
        "pincode": "380001",
        "gstin": RT_COMPANY_GSTIN,
        "gst_category": "Registered Regular",
        "is_your_company_address": 1,
        "links": [{"link_doctype": "Company", "link_name": company}],
    }
    return client.insert(doc)["name"]


def ensure_gst_customer(client: FrappeClient) -> str:
    name = _get_or_create(
        client,
        "Customer",
        RT_GST_CUSTOMER,
        {"customer_name": RT_GST_CUSTOMER, "customer_type": "Company"},
    )
    row = client.get_list("Customer", filters={"name": name}, fields=["gstin"], limit=1)[0]
    if not row.get("gstin"):
        client.call(
            "frappe.client.set_value",
            doctype="Customer",
            name=name,
            fieldname={"gstin": RT_CUSTOMER_GSTIN, "gst_category": "Registered Regular"},
        )
    return name


def ensure_item_tax_template(client: FrappeClient, company: str, rate: int) -> str:
    """Item Tax Template at a GST rate — IC fills the tax rows from ``gst_rate``."""
    existing = client.get_list(
        "Item Tax Template", filters={"company": company, "gst_rate": rate}, fields=["name"], limit=1
    )
    if existing:
        return existing[0]["name"]
    doc = {
        "doctype": "Item Tax Template",
        "title": f"Release GST {rate}%",
        "company": company,
        "gst_treatment": "Taxable",
        "gst_rate": rate,
    }
    return client.insert(doc)["name"]


def ensure_gst_item(client: FrappeClient, company: str, code: str, name: str, rate: int) -> str:
    existing = client.get_list("Item", filters={"name": code}, fields=["name"], limit=1)
    if existing:
        return existing[0]["name"]
    doc = {
        "doctype": "Item",
        "item_code": code,
        "item_name": name,
        "item_group": "All Item Groups",
        "stock_uom": "Nos",
        "is_stock_item": 0,
        "taxes": [{"item_tax_template": ensure_item_tax_template(client, company, rate)}],
    }
    hsn = _hsn_code(client)
    if hsn:
        doc["gst_hsn_code"] = hsn
    return client.insert(doc)["name"]


# ------------------------------------------------------------------ Frappe CRM
RT_CRM_LEAD_EMAIL = "release.lead@example.com"
RT_CRM_LEAD_NAME = "Release"


def ensure_crm_lead(client: FrappeClient) -> str:
    existing = client.get_list("CRM Lead", filters={"email": RT_CRM_LEAD_EMAIL}, fields=["name"], limit=1)
    if existing:
        return existing[0]["name"]
    doc = {
        "doctype": "CRM Lead",
        "first_name": RT_CRM_LEAD_NAME,
        "last_name": "Test Lead",
        "email": RT_CRM_LEAD_EMAIL,
        "status": "New",
    }
    return client.insert(doc)["name"]


def ensure_crm_organization(client: FrappeClient, name: str) -> str:
    existing = client.get_list(
        "CRM Organization", filters={"organization_name": name}, fields=["name"], limit=1
    )
    if existing:
        return existing[0]["name"]
    return client.insert({"doctype": "CRM Organization", "organization_name": name})["name"]


def ensure_crm_deal(client: FrappeClient, organization: str) -> str:
    org = ensure_crm_organization(client, organization)
    existing = client.get_list("CRM Deal", filters={"organization": org}, fields=["name"], limit=1)
    if existing:
        return existing[0]["name"]
    return client.insert({"doctype": "CRM Deal", "organization": org, "status": "Qualification"})["name"]


# ------------------------------------------------------------------ Insights
# Insights v3 stores everything under a Workbook: Queries carry their logic as an
# ``operations`` list (the query-builder format), Charts link a Query, and a
# Dashboard lays out Charts via its ``items`` JSON. Names autogenerate, so all
# get-or-create helpers key on ``title`` (scoped to the workbook where relevant).
RT_INSIGHTS_WORKBOOK = "Release Insights Workbook"
RT_INSIGHTS_QUERY = "Release Sales Invoice Query"
RT_INSIGHTS_DASHBOARD = "Release Sales Invoice Dashboard"


def _insights_by_title(
    client: FrappeClient, doctype: str, title: str, workbook: str | None = None
) -> str | None:
    filters: dict[str, Any] = {"title": title}
    if workbook:
        filters["workbook"] = workbook
    existing = client.get_list(doctype, filters=filters, fields=["name"], limit=1)
    return existing[0]["name"] if existing else None


def ensure_insights_workbook(client: FrappeClient) -> str:
    name = _insights_by_title(client, "Insights Workbook", RT_INSIGHTS_WORKBOOK)
    if name:
        return name
    return client.insert({"doctype": "Insights Workbook", "title": RT_INSIGHTS_WORKBOOK})["name"]


def ensure_insights_query(client: FrappeClient, workbook: str, table_name: str) -> str:
    """A builder query whose source is a Site-DB table (e.g. ``tabSales Invoice``)."""
    name = _insights_by_title(client, "Insights Query v3", RT_INSIGHTS_QUERY, workbook)
    if name:
        return name
    doc = {
        "doctype": "Insights Query v3",
        "title": RT_INSIGHTS_QUERY,
        "workbook": workbook,
        "use_live_connection": 1,
        "is_builder_query": 1,
        "operations": [
            {"type": "source", "table": {"type": "table", "data_source": "Site DB", "table_name": table_name}}
        ],
    }
    return client.insert(doc)["name"]


def ensure_insights_chart(
    client: FrappeClient, workbook: str, query: str, title: str, chart_type: str
) -> str:
    name = _insights_by_title(client, "Insights Chart v3", title, workbook)
    if name:
        return name
    doc = {
        "doctype": "Insights Chart v3",
        "title": title,
        "workbook": workbook,
        "query": query,
        "chart_type": chart_type,
        "config": {},
    }
    return client.insert(doc)["name"]


def ensure_insights_dashboard(client: FrappeClient, workbook: str, charts: list[str]) -> str:
    name = _insights_by_title(client, "Insights Dashboard v3", RT_INSIGHTS_DASHBOARD, workbook)
    if name:
        return name
    items = [{"id": f"chart-{i + 1}", "type": "chart", "chart": c} for i, c in enumerate(charts)]
    doc = {
        "doctype": "Insights Dashboard v3",
        "title": RT_INSIGHTS_DASHBOARD,
        "workbook": workbook,
        "items": items,
    }
    return client.insert(doc)["name"]


# ------------------------------------------------------------------ Helpdesk
RT_HD_AGENT_EMAIL = "release.agent@example.com"
RT_HD_AGENT_NAME = "Release Agent"
RT_HD_TICKET_SUBJECT = "Release smoke ticket"


def ensure_hd_agent(client: FrappeClient) -> str:
    """Get-or-create an HD Agent (and the backing User). Keyed on the user email."""
    existing = client.get_list("HD Agent", filters={"user": RT_HD_AGENT_EMAIL}, fields=["name"], limit=1)
    if existing:
        return existing[0]["name"]
    if not client.get_list("User", filters={"email": RT_HD_AGENT_EMAIL}, fields=["name"], limit=1):
        client.insert(
            {
                "doctype": "User",
                "email": RT_HD_AGENT_EMAIL,
                "first_name": RT_HD_AGENT_NAME,
                "send_welcome_email": 0,
                "roles": [{"role": "Agent"}],
            }
        )
    return client.insert(
        {"doctype": "HD Agent", "user": RT_HD_AGENT_EMAIL, "agent_name": RT_HD_AGENT_NAME, "is_active": 1}
    )["name"]


def ensure_hd_ticket(client: FrappeClient, raised_by: str) -> str:
    """Get-or-create an HD Ticket (keyed on subject so re-runs don't pile up)."""
    existing = client.get_list(
        "HD Ticket", filters={"subject": RT_HD_TICKET_SUBJECT}, fields=["name"], limit=1
    )
    if existing:
        return existing[0]["name"]
    doc = {
        "doctype": "HD Ticket",
        "subject": RT_HD_TICKET_SUBJECT,
        "description": "Opened by the release_tests smoke run.",
        "raised_by": raised_by,
        "priority": "Low",
        "status": "Open",
    }
    return client.insert(doc)["name"]


# ------------------------------------------------------------------ Webshop
RT_WEBSHOP_ITEM = "RT-WEB-ITEM"
RT_WEBSHOP_ITEM_NAME = "Release Web Item"
RT_TOP_BAR_LABEL = "Release Shop"


def ensure_webshop_item(client: FrappeClient) -> str:
    """A stock Item that a Website Item can be published from."""
    return _new_item(client, RT_WEBSHOP_ITEM, RT_WEBSHOP_ITEM_NAME, {"is_stock_item": 0})


def ensure_website_item(client: FrappeClient, item_code: str) -> dict[str, Any]:
    """Get-or-create a *published* Website Item for ``item_code``. Returns name + route."""
    existing = client.get_list(
        "Website Item", filters={"item_code": item_code}, fields=["name", "route", "published"], limit=1
    )
    if existing:
        return existing[0]
    doc = {
        "doctype": "Website Item",
        "item_code": item_code,
        "web_item_name": RT_WEBSHOP_ITEM_NAME,
        "item_group": "All Item Groups",
        "published": 1,
    }
    created = client.insert(doc)
    return {"name": created["name"], "route": created.get("route"), "published": created.get("published")}


def ensure_top_bar_item(client: FrappeClient, label: str, url: str) -> None:
    """Add a Top Bar Item to Website Settings (a Single) if the label isn't already there."""
    settings = client.get_doc("Website Settings", "Website Settings")
    rows = settings.get("top_bar_items") or []
    if any(r.get("label") == label for r in rows):
        return
    rows.append({"doctype": "Top Bar Item", "label": label, "url": url})
    settings["top_bar_items"] = rows
    client.call("frappe.client.save", doc=_json(settings))


# ------------------------------------------------------------------ Builder
RT_BUILDER_ROUTE = "release-test-page"
RT_BUILDER_TITLE = "Release Test Page"


def _builder_text(tag: str, text: str) -> dict[str, Any]:
    return {"element": tag, "attributes": {}, "classes": [], "baseStyles": {}, "children": [], "innerHTML": text}


def _builder_card(title: str, body: str) -> dict[str, Any]:
    return {
        "element": "div",
        "attributes": {},
        "classes": [],
        "baseStyles": {"padding": "20px", "border": "1px solid #eee", "borderRadius": "8px"},
        "children": [_builder_text("h3", title), _builder_text("p", body)],
    }


def _builder_blocks() -> list[dict[str, Any]]:
    """A minimal page: a hero section + a row of three cards."""
    hero = {
        "element": "section",
        "attributes": {},
        "classes": [],
        "baseStyles": {"padding": "60px", "textAlign": "center"},
        "children": [
            _builder_text("h1", "Release Test Page"),
            _builder_text("p", "Published by the release_tests smoke run."),
        ],
    }
    cards = {
        "element": "div",
        "attributes": {},
        "classes": [],
        "baseStyles": {"display": "flex", "gap": "20px", "padding": "40px"},
        "children": [
            _builder_card("Fast", "Reliable release checks."),
            _builder_card("Simple", "One flow per app."),
            _builder_card("Repeatable", "Idempotent by design."),
        ],
    }
    return [hero, cards]


def ensure_builder_page(client: FrappeClient) -> dict[str, Any]:
    """Get-or-create a *published* Builder Page (hero + cards). Returns name + route."""
    existing = client.get_list(
        "Builder Page", filters={"route": RT_BUILDER_ROUTE}, fields=["name", "route", "published"], limit=1
    )
    if existing:
        return existing[0]
    doc = {
        "doctype": "Builder Page",
        "page_title": RT_BUILDER_TITLE,
        "route": RT_BUILDER_ROUTE,
        "blocks": _json(_builder_blocks()),
        "published": 1,
    }
    created = client.insert(doc)
    return {"name": created["name"], "route": created.get("route"), "published": created.get("published")}


# ----------------------------------------------------------- limited-role user
RT_LIMITED_USER = "release.limited@example.com"
# Deliberately ordinary roles. Never System Manager — that bypasses the very
# checks these regressions were about.
RT_LIMITED_ROLES = ("Sales User",)

# Regenerated per process, never written down. A fixed password committed here
# would be a working credential on every site the suite has ever touched, for
# anyone who can read the repo; the suite only needs it for the login it performs
# moments later in the same run.
_LIMITED_PASSWORD = secrets.token_urlsafe(24) + "aA1!"


def limited_password() -> str:
    """The current run's password for :data:`RT_LIMITED_USER`."""
    return _LIMITED_PASSWORD


def ensure_limited_user(client: FrappeClient) -> str:
    """Get-or-create a non-System-Manager user, and set this run's password on it.

    The permission-hardening regressions upstream all look identical from an
    Administrator session — Administrator bypasses the checks that broke. Proving
    those flows still work needs a genuinely restricted login, so this user carries
    ordinary roles only and never System Manager.

    The password is rotated on every run rather than fixed, so the account left
    behind on a target is not usable by anyone holding a copy of this repository.
    """
    existing = client.get_list(
        "User", filters={"name": RT_LIMITED_USER}, fields=["name"], limit=1
    )
    if not existing:
        client.insert(
            {
                "doctype": "User",
                "email": RT_LIMITED_USER,
                "first_name": "Release",
                "last_name": "Limited",
                "send_welcome_email": 0,
                "new_password": _LIMITED_PASSWORD,
                "roles": [{"role": role} for role in RT_LIMITED_ROLES],
            }
        )
        return RT_LIMITED_USER

    client.call(
        "frappe.client.set_value",
        doctype="User",
        name=RT_LIMITED_USER,
        fieldname="new_password",
        value=_LIMITED_PASSWORD,
    )
    return RT_LIMITED_USER
