"""Inspect effective controller chains locally, including multi-app overrides."""

import frappe

from release_tests.diamo_contracts import CONTROLLERS, RPC_OVERRIDES


def check_runtime_contracts():
    from frappe.model.base_document import get_controller

    errors = []
    for doctype, expected in CONTROLLERS.items():
        controller = get_controller(doctype)
        chain = {f"{cls.__module__}.{cls.__name__}" for cls in controller.__mro__}
        for path in expected:
            if path not in chain:
                errors.append(f"Diamo override missing from {doctype} controller chain: {path}.")
    for method, expected in RPC_OVERRIDES.items():
        actual = frappe.override_whitelisted_method(method)
        if actual != expected:
            errors.append(f"Diamo RPC override changed: {method} resolves to {actual}, expected {expected}.")
    return errors
