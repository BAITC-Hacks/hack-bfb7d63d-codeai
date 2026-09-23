from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_demo_workflow_shows_synthetic_source_and_validation_result():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Деректер және граф"
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
