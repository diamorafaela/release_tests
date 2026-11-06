"""Diamo baseline contracts. Changes require review, not runtime feature detection."""

FIELDS = {
    "User": {"enable_api_access": ("Check", None)},
    "Payment Entry": {"modes_of_payment": ("Table", "Payment Entry Mode of Payment")},
    "Sales Invoice": {"punto_de_venta": ("Link", "Punto de Venta")},
    "Purchase Invoice": {
        "tipo_de_comprobante": ("Link", "Tipo de Comprobante"),
        "punto_de_venta": ("Data", None),
        "condicion_de_iva_proveedor": ("Link", "Condicion de IVA"),
    },
    "Customer": {"impuestos_de_percepcion": ("Table", "Impuesto Percepcion Cliente")},
    "Supplier": {"impuestos_de_retencion": ("Table", "Impuesto Retencion Proveedor")},
}

CONTROLLERS = {
    "User": ("diamoerp_base.overrides.user.DiamoERPUser",),
    "User Type": ("diamoerp_base.overrides.user_type.DiamoERPUserType",),
    "Translation": ("diamoerp_base.overrides.translation.DiamoERPTranslation",),
    "Role Replication": ("diamoerp_base.overrides.role_replication.DiamoERPRoleReplication",),
    "Sales Invoice": ("diamoerp_argentina.overrides.sales_invoice.CustomSalesInvoice",),
    "Purchase Invoice": ("diamoerp_argentina.overrides.purchase_invoice.CustomPurchaseInvoice",),
    "Payment Entry": ("diamoerp_argentina.overrides.payment_entry.CustomPaymentEntry",),
    "Sales Invoice Item": ("diamoerp_argentina.overrides.sales_invoice_item.CustomSalesInvoiceItem",),
    "Customer": ("diamoerp_argentina.overrides.customer.CustomCustomer",),
    "Selling Settings": ("diamoerp_argentina.overrides.selling_settings.CustomSellingSettings",),
    "Purchase Order": ("diamoerp_argentina.overrides.purchase_order.CustomPurchaseOrder",),
    "Company": ("diamoerp_argentina.overrides.company.CustomCompany",),
    "Subscription": ("diamoerp_argentina.overrides.subscription.CustomSubscription",),
    "Process Subscription": ("diamoerp_argentina.overrides.process_subscription.CustomProcessSubscription",),
    "Subscription Plan": ("diamoerp_argentina.overrides.subscription_plan.CustomSubscriptionPlan",),
    "Opening Invoice Creation Tool": ("diamoerp_argentina.overrides.opening_invoice_creation_tool.CustomOpeningInvoiceCreationTool",),
    "Payment Request": (
        "diamoerp_argentina.overrides.payment_request.CustomPaymentRequest",
        "diamoerp_argentina.diamoerp_argentina.doctype.pagos360_settings.pagos360_settings.Pagos360PaymentRequestMixin",
    ),
    "GL Entry": ("diamoerp_argentina.overrides.gl_entry.CustomGLEntry",),
    "Sales Order": ("diamoerp_argentina.overrides.sales_order.CustomSalesOrder",),
    "Journal Entry": (
        "diamoerp_base.overrides.journal_entry.JournalEntryMixin",
        "diamoerp_argentina.overrides.journal_entry.CustomJournalEntry",
    ),
}

# Critical RPC bindings must survive changes in app order and upstream endpoints.
RPC_OVERRIDES = {
    "frappe.core.doctype.user.user.generate_keys": "diamoerp_base.overrides.user.generate_keys",
    "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry":
        "diamoerp_argentina.overrides.payment_entry.get_payment_entry",
    "erpnext.accounts.doctype.payment_entry.payment_entry.get_reference_details":
        "diamoerp_argentina.overrides.payment_entry.get_reference_details",
    "erpnext.accounts.doctype.subscription_plan.subscription_plan.get_plan_rate":
        "diamoerp_argentina.overrides.subscription_plan.get_plan_rate",
}

CORE_SUITES = (
    "core_frappe", "diamo_customizations", "diamo_frappe_filters",
    "diamo_argentina_buying", "diamo_argentina_payments", "diamo_base_access",
    "diamo_combined_receipts", "diamo_perceptions", "diamo_withholdings", "diamo_service_credits",
    "diamo_purchase_contracts", "erpnext", "erpnext_accounts", "erpnext_stock",
    "erpnext_buying", "erpnext_selling", "erpnext_service", "erpnext_serialised",
    "erpnext_batched", "erpnext_manufacturing", "frappe_jinja_sandbox", "frappe_permissions",
)
