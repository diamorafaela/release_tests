import pytest

from release_tests.site_setup import DEFAULT_SUITES, select_suites


def test_default_suites_are_registered():
    assert select_suites(list(DEFAULT_SUITES)) == list(DEFAULT_SUITES)


def test_selection_rejects_unknown_or_empty_suites():
    for value in ([], ["not_a_suite"], "", {}):
        with pytest.raises(ValueError):
            select_suites(value)


def test_selection_deduplicates_cli_values():
    assert select_suites("core_frappe, core_frappe") == ["core_frappe"]
    assert select_suites('["core_frappe", "crm"]') == ["core_frappe", "crm"]
