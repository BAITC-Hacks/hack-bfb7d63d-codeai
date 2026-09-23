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


def test_cross_page_map_navigation_preserves_dataset_and_exact_ids(monkeypatch):
    from types import SimpleNamespace
    import moneymap.ui_state as ui_state
    import moneymap.ui_map as ui_map

    class State(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    gid = 100000008686313100
    validation = object()
    analysis = SimpleNamespace(graph={gid, gid + 100})
    roles = SimpleNamespace(details=pd.DataFrame({"gid": [gid, gid + 100], "cluster_id": [3, 3], "priority_score": [.9, .7]}))
    state = State(validation=validation, analysis=analysis, role_analysis=roles,
                  map_mode="full", map_role_filters=["terminal"], map_min_amount=999999.0)
    ui = SimpleNamespace(session_state=state, error=lambda text: pytest.fail(text))
    monkeypatch.setattr(ui_state, "st", ui)
    monkeypatch.setattr(ui_map, "st", ui)
    ui_state.queue_map_navigation(gid=str(gid), rerun=False)
    # The old widget value is untouched until the next page begins rendering.
    assert state.map_mode == "full"
    assert state.pending_workspace_page == "Желі картасы"
    ui_map.apply_pending_map_navigation()
    assert state.validation is validation and state.analysis is analysis and state.role_analysis is roles
    assert state.map_ready and state.map_selected_gid == str(gid)
    assert state.map_mode == "ego" and state.map_role_filters == [] and state.map_min_amount == 0
    ui_state.queue_map_navigation(cluster_id=3, rerun=False)
    ui_map.apply_pending_map_navigation()
    assert state.map_mode == "cluster" and state.map_cluster_filter == 3
    assert state.map_focus_gid == str(gid)  # No int64 -> floating row conversion.
    assert state.map_color == "cluster"
    assert "map_pending_navigation" not in state


@pytest.mark.parametrize("arguments", [{}, {"gid": "123", "cluster_id": 1}, {"gid": 1.5}])
def test_map_navigation_rejects_ambiguous_or_inexact_targets(arguments):
    from moneymap.ui_state import queue_map_navigation
    with pytest.raises(ValueError):
        queue_map_navigation(**arguments, rerun=False)
