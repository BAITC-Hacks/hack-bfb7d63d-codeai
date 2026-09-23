from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_investigation_workflow_recomputes_parameters_and_clears_stale_results():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    app.button(key="inv_prepare").click().run()
    assert not app.exception
    assert app.session_state["inv_ready"]
    assert len(app.session_state["analysis"].nodes) == 16
    app.selectbox(key="inv_gid").select("1004").run()
    assert not app.exception
    assert any("1004" in element.value for element in app.markdown)
    app.button(key="inv_compute_routes").click().run()
    assert not app.exception
    assert app.session_state["inv_routes_window"] == 2
    app.selectbox(key="inv_window").select(1).run()
    assert any("Таңдалған уақыт аралығымен" in item.value for item in app.info)
    app.button(key="inv_compute_routes").click().run()
    assert app.session_state["inv_routes_window"] == 1
    app.button(key="inv_compute_resilience").click().run()
    assert not app.exception
    assert len(app.session_state["inv_resilience"].removed_gids) == 5
    app.number_input(key="inv_top_n").set_value(16).run()
    assert any("Клиент санын таңдап" in item.value for item in app.info)
    app.button(key="inv_compute_resilience").click().run()
    assert not app.exception
    assert len(app.session_state["inv_resilience"].remaining_gids) == 0
    app.button(key="compute_roles").click().run()
    assert not app.exception
    assert "inv_ready" not in app.session_state
    assert "inv_routes" not in app.session_state
    assert "inv_resilience" not in app.session_state
    app.button(key="inv_prepare").click().run()
    app.button(key="compute_graph").click().run()
    assert "inv_ready" not in app.session_state
    app.button(key="inv_prepare").click().run()
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    assert not app.exception
    assert "inv_ready" not in app.session_state
