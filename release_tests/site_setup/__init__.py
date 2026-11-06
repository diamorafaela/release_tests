"""Local administrative preparation, invoked with bench execute (never whitelisted)."""

DEFAULT_SUITES = (
    "core_frappe", "crm", "erpnext", "erpnext_accounts", "frappe_filters",
    "diamo_argentina_payments", "diamo_argentina_buying", "diamo_service_credits",
    "diamo_combined_receipts", "diamo_perceptions", "diamo_withholdings", "diamo_base_access",
)
QA_USER = "release-qa@example.com"
QA_ROLE = "Release Test Executor"
COMPANY = "Diamo Release Test"


def prepare(suites=None, profile_path=None):
    """Create missing QA fixtures and report unmet prerequisites without changing license limits."""
    import frappe

    from .fixtures import AccountingFixtures
    from .identity import ensure_executor
    from .preflight import Preflight

    require_administrator()
    selected = profile_suites(suites, profile_path)
    previous = frappe.conf.developer_mode
    try:
        # Fixture saves must not export files into the candidate repositories.
        frappe.conf.developer_mode = 0
        if "erpnext" in frappe.get_installed_apps():
            AccountingFixtures().prepare(fiscal=bool(set(selected) & {"diamo_perceptions", "diamo_withholdings"}))
        identity_errors = ensure_executor(selected)
        if set(selected) & {"frappe_filters", "diamo_frappe_filters", "customisations"}:
            ensure_filter_probe()
        result = Preflight(selected, QA_USER).run()
        result["blockers"] = list(dict.fromkeys(identity_errors + result["blockers"]))
        result["ready"] = not result["blockers"]
        frappe.db.commit()
        return result
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.conf.developer_mode = previous


def check(suites=None, user=QA_USER, profile_path=None):
    """Read-only readiness report; does not execute suites or create fixtures."""
    from .preflight import Preflight

    require_administrator()
    return Preflight(profile_suites(suites, profile_path), user).run()


def profile_suites(suites, profile_path):
    import json
    from pathlib import Path

    if profile_path is None:
        return select_suites(suites)
    if suites is not None:
        raise ValueError("Supply either suites or profile_path, not both.")
    profile = json.loads(Path(profile_path).read_text())
    if isinstance(profile, dict):
        profile = profile["profile_snapshot"]
    if isinstance(profile, str):
        profile = json.loads(profile)
    return select_suites([row["suite"] for row in profile])


def select_suites(suites):
    import json

    from release_tests.api import catalog

    if suites is None:
        return list(DEFAULT_SUITES)
    if suites == "diamo":
        from release_tests.diamo_contracts import CORE_SUITES

        return list(CORE_SUITES)
    if isinstance(suites, str):
        suites = json.loads(suites) if suites.startswith("[") else suites.split(",")
    if not isinstance(suites, (list, tuple)) or not suites:
        raise ValueError("Supply a nonempty list of suite names.")
    names = list(dict.fromkeys(name.strip() for name in suites))
    unknown = set(names) - {row["suite"] for row in catalog()}
    if unknown:
        raise ValueError("Unknown suites: " + ", ".join(sorted(unknown)))
    return names


def require_administrator():
    import frappe

    if frappe.session.user != "Administrator":
        frappe.throw("Run this local command as Administrator.", frappe.PermissionError)


def ensure_filter_probe():
    import frappe

    from release_tests.customisations import RT_API_SCRIPT, _fixture

    from .fixtures import ensure

    if not frappe.get_common_site_config().get("server_script_enabled"):
        return
    definition = next(row for row in _fixture("server_scripts.json") if row["name"] == RT_API_SCRIPT)
    ensure("Server Script", definition["name"], definition)
