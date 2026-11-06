import json
from unittest.mock import Mock

import pytest

from release_tests.factories import ensure_company
from release_tests.site_setup import COMPANY, profile_suites


def test_prepared_company_wins_over_unrelated_company():
    client = Mock()
    client.get_list.side_effect = lambda dt, **kw: [
        {"name": COMPANY if kw.get("filters") == {"name": COMPANY} else "Unprepared Company"}
    ]
    assert ensure_company(client) == COMPANY


def test_generic_sites_keep_existing_company():
    client = Mock()
    client.get_list.side_effect = [[], [{"name": "Existing Company"}]]
    assert ensure_company(client) == "Existing Company"
    client.insert.assert_not_called()


@pytest.mark.parametrize("export_document", [False, True])
def test_profile_selection_uses_exported_scope(tmp_path, export_document):
    profile = [{"case": "Core", "suite": "core_frappe"}, {"case": "HR", "suite": "hrms"}]
    path = tmp_path / "validation.json"
    data = {"profile_snapshot": json.dumps(profile)} if export_document else profile
    path.write_text(json.dumps(data))
    assert profile_suites(None, path) == ["core_frappe", "hrms"]
    with pytest.raises(ValueError):
        profile_suites(["crm"], path)
