"""Baseline range behavior of the Diamo fork, independent of polished-only features."""

from . import frappe_filters as filters
from .base import CheckFailed, ReleaseSuite, Step


class DiamoFrappeFiltersSuite(ReleaseSuite):
    name = "diamo_frappe_filters"
    required_app = "diamoerp_base"
    description = "Diamo Date/Datetime database ranges and supported Python >=/<= filters agree, including excluded dates."

    def build_steps(self, versions):
        return [
            Step("seed isolated dated ToDos", filters._seed),
            Step("between on a Date field", filters._between_on_date),
            Step("capitalised Between matches between", filters._between_capitalised),
            Step("both bounds are inclusive", filters._bounds_are_inclusive),
            Step("Datetime upper bound covers end of day", filters._datetime_end_of_day),
            Step("supported Python range agrees with DB", self.python_range),
        ]

    def python_range(self, client, ctx):
        for label, date in (("d1", filters._D1), ("d2", filters._D2), ("d3", filters._D3)):
            actual = filters._probe(client, {"doctype": "ToDo", "date": date}, [
                ["date", ">=", filters._RANGE[0]], ["date", "<=", filters._RANGE[1]],
            ])
            expected = ctx["todos"][label] in ctx["db_result"]
            if actual != expected:
                raise CheckFailed("Python and DB range agreement", expected=str(expected), actual=str(actual),
                                  hint=f"Date {date}; review evaluate_filters casting after the framework upgrade.")
