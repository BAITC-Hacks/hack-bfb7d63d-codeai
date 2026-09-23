from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_demo_workflow_shows_synthetic_source_and_validation_result():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Қаржылық желіні талдау"
    demo_button = next(button for button in app.button if button.label == "Демо деректермен тексеру")
    demo_button.click().run()
    assert not app.exception
    assert app.session_state["source"] == "demo"
    assert app.session_state["validation"].valid
    assert any("ДЕМО РЕЖИМІ" in warning.value for warning in app.warning)
    assert len(app.metric) == 7
    assert app.metric[0].value == "16"
    assert app.metric[1].value == "15"
    assert app.metric[2].value == "17"
    assert any("келесі талдау кезеңіне дайын" in item.value for item in app.success)

    app.button(key="compute_graph").click().run()
    assert not app.exception
    assert len(app.session_state["analysis"].nodes) == 16
    assert any("16 клиент сақталды" in item.value for item in app.success)
    app.selectbox(key="inspect_gid").select("1004").run()
    assert not app.exception
    assert any("бақыланған байланыстары жоқ" in item.value for item in app.info)
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    assert not app.exception
    assert "analysis" not in app.session_state


def test_roles_can_run_directly_and_are_cleared_when_input_or_graph_changes():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    app.button(key="compute_roles").click().run()
    assert not app.exception
    result = app.session_state["role_analysis"]
    assert len(result.nodes_roles) == len(result.top_nodes) == 16
    assert result.nodes_roles.gid.is_unique
    app.selectbox(key="role_gid").select("1004").run()
    assert not app.exception
    assert any("басымдық 0" in item.value for item in app.info)
    app.button(key="compute_graph").click().run()
    assert not app.exception
    assert "role_analysis" not in app.session_state
    app.button(key="compute_roles").click().run()
    assert "role_analysis" in app.session_state
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    assert not app.exception
    assert "role_analysis" not in app.session_state


def test_map_search_full_network_filters_and_invalidated_results():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    app.button(key="prepare_map").click().run()
    assert not app.exception
    assert app.session_state["map_ready"]
    app.selectbox(key="map_mode").select("full").run()
    assert not app.exception
    assert app.session_state["map_summary"]["visible_nodes"] == 16
    assert app.session_state["map_summary"]["visible_edges"] == 15
    app.text_input(key="map_search").set_value("1004")
    next(button for button in app.button if button.label == "Картадан табу").click().run()
    assert not app.exception
    assert app.session_state["map_selected_gid"] == "1004"
    assert app.session_state["map_summary"]["visible_nodes"] == 1
    assert app.session_state["map_summary"]["visible_edges"] == 0
    assert any("Клиент картада сақталған" in item.value for item in app.info)
    app.multiselect(key="map_role_filters").select("consolidator").run()
    assert not app.exception
    assert app.session_state["map_summary"]["focus_outside_filter"]
    app.text_input(key="map_search").set_value("1004.5")
    next(button for button in app.button if button.label == "Картадан табу").click().run()
    assert not app.exception
    assert app.session_state["map_selected_gid"] == "1004"
    assert any("gid табылмады" in item.value for item in app.error)
    app.button(key="compute_roles").click().run()
    assert not app.exception
    assert "map_ready" not in app.session_state


def test_map_selection_is_confirmed_to_browser_without_replaying_old_events(monkeypatch):
    import moneymap.ui_map as ui_map

    observed = {}
    event = {}

    def component_stub(payload, view_key, widget_key):
        observed.update(payload=payload, view_key=view_key)
        return event or None

    monkeypatch.setattr(ui_map, "render_network", component_stub)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    app.button(key="prepare_map").click().run()
    chosen = next(node["id"] for node in observed["payload"]["nodes"] if node["id"] != observed["payload"]["selected_gid"])
    event.update(gid=chosen, view_key=observed["view_key"], nonce="click-one")
    app.run()
    assert not app.exception
    assert app.session_state["map_selected_gid"] == chosen
    assert observed["payload"]["selected_gid"] == chosen
    app.run()  # Same component value must not trigger another rerun loop.
    assert not app.exception
    assert app.session_state["map_last_nonce"] == "click-one"
    app.button(key="map_recenter").click().run()
    assert not app.exception
    assert app.session_state["map_focus_gid"] == chosen
    assert app.session_state["map_mode"] == "ego"
    assert observed["view_key"] != event["view_key"]
