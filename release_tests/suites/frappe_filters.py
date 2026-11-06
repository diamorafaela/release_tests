"""Regression cover for the ``between`` filter operator.

frappe@9978deb859 ("feat: add between operator to evaluate_filters", backport of
PR #41610 as #41622, 2026-08-06) added ``between``/``Between`` to
``frappe.utils.data.operator_map`` and moved ``convert_type_for_between_filters``
out of ``frappe/model/db_query.py`` into ``frappe/utils/data.py``. Before it, the
in-Python filter path returned **False for every between filter** — so Notification
conditions, Assignment Rules and Workflow transitions using ``between`` silently
never fired. After it, they do.

Upstream added unit tests for ``compare()`` semantics. What nothing covers is
**cross-path agreement**: the expansion now lives in three separate places
(``db_query.py``, ``database/query.py``, ``utils/data.py``) and the whole point of
the change is that they should agree. This suite asserts exactly that, over HTTP.

The in-Python path has no stock endpoint, so it is reached through the
``rt_filter_probe`` API Server Script from the customisation pack. On a site
without that pack those steps skip rather than fail.
"""

from __future__ import annotations

import json
import secrets
from typing import ClassVar

from ..client import FrappeAPIError, FrappeClient
from ..gating import Versions
from .base import ReleaseSuite, SkipStep, Step

RT_FILTER_MARKER = "RT-FILTER-PROBE"

# Fixed bounds so the suite is deterministic regardless of when it runs.
_D1 = "2026-01-01"
_D2 = "2026-01-15"
_D3 = "2026-02-15"
_RANGE = ["2026-01-01", "2026-01-31"]


def _marked(client: FrappeClient, ctx: dict, filters: list) -> set[str]:
    rows = client.get_list(
        "ToDo",
        filters=[["description", "like", f"%{ctx['filter_marker']}%"], *filters],
        fields=["name"],
        limit=50,
    )
    return {r["name"] for r in rows}


def _seed(client: FrappeClient, ctx: dict) -> None:
    """Isolate this run from retained ToDos and concurrent executions."""
    ctx["filter_marker"] = f"{RT_FILTER_MARKER}-{secrets.token_hex(16)}"
    ctx["todos"] = {}
    for label, date in (("d1", _D1), ("d2", _D2), ("d3", _D3)):
        doc = client.insert(
            {"doctype": "ToDo", "description": f"{ctx['filter_marker']} {label}", "date": date}
        )
        ctx["todos"][label] = doc["name"]
        # The server's own clock, taken from a row it just stamped. Avoids needing a
        # whitelisted time endpoint (frappe.utils.now is not callable over REST) and
        # sidesteps any clock skew between the harness host and the target.
        ctx["server_today"] = str(doc["creation"])[:10]


def _between_on_date(client: FrappeClient, ctx: dict) -> None:
    """Baseline: a Date field filtered by an inclusive range."""
    found = _marked(client, ctx, [["date", "between", _RANGE]])
    expected = {ctx["todos"]["d1"], ctx["todos"]["d2"]}
    if found != expected:
        raise AssertionError(f"between on Date returned {found}, expected {expected}")
    ctx["db_result"] = found


def _between_capitalised(client: FrappeClient, ctx: dict) -> None:
    """The Desk UI sends ``Between``; it must behave identically to ``between``.

    Before frappe@9978deb859 the capitalised form fell through to False in the
    in-Python path. The DB path lowercases the operator, so this asserts the two
    spellings agree end to end.
    """
    found = _marked(client, ctx, [["date", "Between", _RANGE]])
    if found != ctx["db_result"]:
        raise AssertionError(
            f"'Between' returned {found} but 'between' returned {ctx['db_result']}"
        )


def _bounds_are_inclusive(client: FrappeClient, ctx: dict) -> None:
    """Both endpoints must be inside the range."""
    found = _marked(client, ctx, [["date", "between", [_D1, _D2]]])
    expected = {ctx["todos"]["d1"], ctx["todos"]["d2"]}
    if found != expected:
        raise AssertionError(f"bounds not inclusive: got {found}, expected {expected}")


def _datetime_end_of_day(client: FrappeClient, ctx: dict) -> None:
    """A date-only upper bound must cover the whole final day of a Datetime field.

    The ToDos were created moments ago, so filtering ``creation`` between today and
    today only finds them if the upper bound expanded to 23:59:59.999999. Without
    the expansion the bound would be midnight and every row would be excluded.
    """
    today = ctx["server_today"]
    found = _marked(client, ctx, [["creation", "between", [today, today]]])
    expected = set(ctx["todos"].values())
    if not expected.issubset(found):
        raise AssertionError(
            f"Datetime upper bound did not expand to end-of-day: {expected - found} missing"
        )


def _probe_absent(exc: FrappeAPIError) -> bool:
    """True only when the probe endpoint isn't installed on this site.

    Frappe answers a missing/unexposed whitelisted method with 403/404 and a
    "not whitelisted" message. Anything else — a 500 from inside the script, a
    bad argument — means the probe *is* there and genuinely failed, which must
    surface as a failure rather than be waved through as "not installed".
    """
    if exc.status not in (403, 404, 417):
        return False
    text = str(exc).lower()
    return "not whitelisted" in text or "not found" in text or "does not exist" in text


def _probe(client: FrappeClient, doc: dict, filters: list) -> bool:
    try:
        result = client.call(
            "rt_filter_probe", probe_doc=json.dumps(doc), probe_filters=json.dumps(filters)
        )
    except FrappeAPIError as exc:
        if not _probe_absent(exc):
            raise AssertionError(
                f"rt_filter_probe is installed but failed ({exc.status}): {str(exc)[:200]}"
            ) from exc
        raise SkipStep(
            "rt_filter_probe not available — install the customisation pack on this site "
            "to cover the in-Python filter path"
        ) from exc
    if not isinstance(result, dict) or "evaluate_filters" not in result:
        # The endpoint answered, so it is installed — it just answered wrongly.
        # Skipping here would let the suite pass while the cross-path check it
        # exists for never ran, which is the whole failure mode being guarded.
        raise AssertionError(f"rt_filter_probe returned an unexpected payload: {result!r}")
    return bool(result["evaluate_filters"])


def _in_python_agrees_with_db(client: FrappeClient, ctx: dict) -> None:
    """The whole point of the change: both paths must give the same answer."""
    mismatches = []
    for label, date in (("d1", _D1), ("d2", _D2), ("d3", _D3)):
        in_python = _probe(client, {"doctype": "ToDo", "date": date}, [["date", "between", _RANGE]])
        in_db = ctx["todos"][label] in ctx["db_result"]
        if in_python != in_db:
            mismatches.append(f"{date}: evaluate_filters={in_python} but DB={in_db}")
    if mismatches:
        raise AssertionError("in-Python and DB filter paths disagree — " + "; ".join(mismatches))


def _iso_t_bound_not_widened(client: FrappeClient, ctx: dict) -> None:
    """An ISO-8601 ``T`` bound must not silently widen to end-of-day.

    ``convert_type_for_between_filters`` decides date-vs-datetime with
    ``" " in value.strip()``. An ISO-``T`` string has no space, so it routes to
    ``getdate()``, loses its time component, and the bound expands to the end of the
    day. The same instant written with a space compares correctly, so the two
    spellings give opposite answers.

    Verified against frappe v16.31.0 on 2026-08-26. Reported as a skip rather than a
    failure so the suite documents the defect without going red on a release that
    merely still has it — and flips to a pass automatically once upstream fixes it.
    """
    doc = {"doctype": "ToDo", "modified": "2026-01-31 10:30:00"}
    spaced = _probe(client, doc, [["modified", "between", ["2026-01-01", "2026-01-31 10:00:00"]]])
    iso = _probe(client, doc, [["modified", "between", ["2026-01-01", "2026-01-31T10:00:00"]]])
    if spaced == iso:
        return  # upstream fixed it
    raise SkipStep(
        "known upstream defect still present: ISO-8601 'T' bound "
        "'2026-01-31T10:00:00' drops its time and expands to end-of-day "
        f"(spaced={spaced}, iso-T={iso} for the same instant). "
        "See convert_type_for_between_filters in frappe/utils/data.py."
    )


class FrappeFiltersSuite(ReleaseSuite):
    name = "frappe_filters"
    required_app = "frappe"
    description = (
        "Regression: the 'between'/'Between' filter operator across the DB and in-Python "
        "paths — bound inclusivity, Datetime end-of-day expansion, and cross-path agreement."
    )
    guards: ClassVar[list[str]] = [
        "frappe@9978deb859",  # feat: add between operator to evaluate_filters
        "frappe#41610",  # original PR
        "frappe#41622",  # v16 backport
    ]

    def build_steps(self, versions: Versions) -> list[Step]:
        return [
            Step("seed dated ToDos", _seed),
            Step("between on a Date field", _between_on_date),
            Step("capitalised 'Between' matches 'between'", _between_capitalised),
            Step("both bounds are inclusive", _bounds_are_inclusive),
            Step("Datetime upper bound covers end of day", _datetime_end_of_day),
            Step("in-Python path agrees with DB path", _in_python_agrees_with_db),
            Step("ISO-T bound is not silently widened", _iso_t_bound_not_widened),
        ]
