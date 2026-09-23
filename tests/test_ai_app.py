from pathlib import Path

from streamlit.testing.v1 import AppTest


def app_ready(monkeypatch):
    from moneymap.ai_settings import AISettings, SUPPORTED_MODELS

    monkeypatch.setenv("MONEYMAP_AI_ENABLED", "false")
    monkeypatch.setattr("moneymap.ui_ai.load_settings", lambda provider, **kwargs: AISettings(provider, SUPPORTED_MODELS[provider], "", enabled=False))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    go(app, "Анықтама")
    app.button(key="prepare_ai").click().run()
    assert not app.exception
    return app


def go(app, page):
    app.radio(key="workspace_page").set_value(page).run()


def test_local_assistant_needs_no_key_and_resets_on_input_or_role_change(monkeypatch):
    app = app_ready(monkeypatch)
    assert app.button(key="ai_generate").disabled
    app.selectbox(key="ai_gid").select("1004").run()
    app.button(key="ai_local").click().run()
    assert not app.exception
    assert "AI қолданылған жоқ" in app.session_state["ai_output"]["report"]
    assert "1004" in app.session_state["ai_output"]["report"]
    assert app.session_state["ai_output"]["origin"] == "explicit_local"
    assert any("API сұрауы жіберілген жоқ" in item.value for item in app.success)
    app.selectbox(key="ai_task").select("top_priority").run()
    assert "ai_output" not in app.session_state
    app.button(key="ai_local").click().run()
    assert not app.exception
    go(app, "Тексеру кезегі")
    app.button(key="compute_roles").click().run()
    assert "ai_ready" not in app.session_state and "ai_output" not in app.session_state
    go(app, "Анықтама")
    app.button(key="prepare_ai").click().run()
    go(app, "Шолу")
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    assert "ai_ready" not in app.session_state


def test_common_recipients_requires_distinct_known_gids_and_provider_is_explicit(monkeypatch):
    app = app_ready(monkeypatch)
    app.selectbox(key="ai_task").select("common_recipients").run()
    app.text_area(key="ai_gids").set_value("1001, 1001").run()
    assert not app.exception
    assert any("әртүрлі gid" in item.value for item in app.info)
    app.text_area(key="ai_gids").set_value("1001, 1002").run()
    assert not app.exception
    app.selectbox(key="ai_provider").select("nvidia").run()
    assert app.button(key="ai_generate").disabled
    app.button(key="ai_local").click().run()
    assert not app.exception
    assert app.session_state["ai_output"]["local"]


def test_api_failure_falls_back_to_local_report_and_graph_still_works(monkeypatch):
    from moneymap.ai_provider import AIProviderError
    from moneymap.ai_settings import AISettings, OPENAI_MODEL

    app = app_ready(monkeypatch)
    monkeypatch.setattr("moneymap.ui_ai.load_settings", lambda *args, **kwargs: AISettings("openai", OPENAI_MODEL, "test-fake-key", enabled=True))
    monkeypatch.setattr("moneymap.ui_ai.BudgetLedger", lambda *args: None)

    def unavailable(*args, **kwargs):
        raise AIProviderError("timeout", "AI жауап беру уақытынан асты.")

    monkeypatch.setattr("moneymap.ui_ai.request_analysis", unavailable)
    app.run()
    app.button(key="ai_generate").click().run()
    assert not app.exception
    assert any("уақытынан асты" in item.value for item in app.warning)
    assert app.session_state["ai_output"]["local"]
    assert app.session_state["ai_output"]["origin"] == "api_fallback"
    assert not any("API шығыны жоқ" in item.value or "API сұрауы жіберілген жоқ" in item.value for item in app.success)
    assert any("шығыны болуы мүмкін" in item.value for item in app.info)
    assert "AI қолданылған жоқ" in app.session_state["ai_output"]["report"]
    go(app, "Деректер")
    app.button(key="compute_graph").click().run()
    assert not app.exception
    assert len(app.session_state["analysis"].nodes) == 16


def test_analyst_note_opens_the_exact_selected_client_on_map(monkeypatch):
    app = app_ready(monkeypatch)
    app.selectbox(key="ai_gid").select("1004").run()
    app.button(key="ai_local").click().run()
    app.button(key="ai_open_map").click().run()
    assert not app.exception
    assert app.radio(key="workspace_page").value == "Желі картасы"
    assert app.session_state["map_selected_gid"] == "1004"
    assert len(app.session_state["analysis"].nodes) == 16
