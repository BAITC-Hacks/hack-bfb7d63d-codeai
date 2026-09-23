from pathlib import Path
import re

import pytest

from moneymap.map_component import selected_from_event
from moneymap.ui_graph import safe_identifiers
import pandas as pd


def test_selection_keeps_exact_string_id_and_rejects_repeated_or_stale_click():
    gid = str(2**63 - 1)
    event = {"gid": gid, "view_key": "current", "nonce": "unique"}
    assert selected_from_event(event, "current", {gid}) == gid
    assert selected_from_event(event, "current", {gid}, "unique") is None
    assert selected_from_event(event, "new-dataset", {gid}) is None
    assert selected_from_event(event, "current", {"1004"}) is None


@pytest.mark.parametrize("event", [None, [], "bad", {}, {"gid": 1004, "nonce": "a", "view_key": "v"}, {"gid": "1004", "nonce": "", "view_key": "v"}, {"gid": "1004", "nonce": 1, "view_key": "v"}])
def test_malformed_component_event_cannot_select_a_client(event):
    assert selected_from_event(event, "v", {"1004"}) is None


def test_neighbor_ids_are_text_for_browser_but_input_is_not_mutated():
    gid = 2**63 - 1
    frame = pd.DataFrame({"src": [gid], "dst": [gid - 1], "counterparty_gid": [gid - 1]})
    safe = safe_identifiers(frame)
    assert safe.loc[0, "src"] == str(gid)
    assert safe.loc[0, "counterparty_gid"] == str(gid - 1)
    assert frame.loc[0, "src"] == gid


def test_component_bootstrap_loads_only_bundled_resources():
    base = Path(__file__).resolve().parents[1] / "moneymap" / "graph_component"
    html = (base / "index.html").read_text(encoding="utf-8")
    resources = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert resources
    for resource in resources:
        assert not resource.startswith(("http:", "https:", "//"))
        assert (base / resource).is_file()
