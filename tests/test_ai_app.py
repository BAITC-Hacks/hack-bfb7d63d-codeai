from pathlib import Path

from streamlit.testing.v1 import AppTest


def app_ready(monkeypatch):
    monkeypatch.setenv("MONEYMAP_AI_ENABLED", "false")
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    app.button(key="prepare_ai").click().run()
    assert not app.exception
    return app


def test_local_assistant_needs_no_key_and_resets_on_input_or_role_change(monkeypatch):
    app = app_ready(monkeypatch)
    assert app.button(key="ai_generate").disabled
    app.selectbox(key="ai_gid").select("1004").run()
    app.button(key="ai_local").click().run()
    assert not app.exception
    assert "AI қолданылған жоқ" in app.session_state["ai_output"]["report"]
    assert "1004" in app.session_state["ai_output"]["report"]
    app.selectbox(key="ai_task").select("top_priority").run()
    assert "ai_output" not in app.session_state
    app.button(key="ai_local").click().run()
    assert not app.exception
    app.button(key="compute_roles").click().run()
    assert "ai_ready" not in app.session_state and "ai_output" not in app.session_state
    app.button(key="prepare_ai").click().run()
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
    assert "AI қолданылған жоқ" in app.session_state["ai_output"]["report"]
    app.button(key="compute_graph").click().run()
    assert not app.exception
    assert len(app.session_state["analysis"].nodes) == 16


def test_text_question_returns_local_facts_rejects_unknown_and_clears_stale_results(monkeypatch):
    def no_provider(*args, **kwargs):
        raise AssertionError("A local question must not invoke an AI provider")

    monkeypatch.setattr("moneymap.ui_ai.request_analysis", no_provider)
    app = app_ready(monkeypatch)
    app.radio(key="ai_mode").set_value("Сұрақ жазу").run()
    app.text_area(key="ai_question").set_value("Кіріс және шығыс 1005").run()
    app.button(key="ai_ask_question").click().run()
    assert not app.exception
    assert app.session_state["ai_output"]["local"]
    report = app.session_state["ai_output"]["report"]
    assert "1005" in report and "220000" in report and "200000" in report
    assert app.button(key="ai_generate").disabled
    app.text_area(key="ai_question").set_value("Неге 999999 маңызды?").run()
    assert "ai_output" not in app.session_state
    assert "ai_question_bundle" not in app.session_state
    app.button(key="ai_ask_question").click().run()
    assert not app.exception
    assert any("деректер жиынында жоқ" in item.value for item in app.info)
    assert "ai_output" not in app.session_state
    app.text_area(key="ai_question").set_value("Каких данных не хватает для 1014?").run()
    app.button(key="ai_ask_question").click().run()
    assert "Төртінші буыннан" in app.session_state["ai_output"]["report"]
    app.button(key="compute_graph").click().run()
    assert not app.exception
    assert "ai_question_bundle" not in app.session_state and "ai_ready" not in app.session_state


def test_text_question_optional_ai_receives_canonical_facts_only_after_explicit_button(monkeypatch):
    import json

    from moneymap.ai_settings import AISettings, OPENAI_MODEL

    received = []
    app = app_ready(monkeypatch)
    monkeypatch.setattr("moneymap.ui_ai.load_settings", lambda *args, **kwargs: AISettings("openai", OPENAI_MODEL, "test-fake-key", enabled=True))
    monkeypatch.setattr("moneymap.ui_ai.BudgetLedger", lambda *args: None)

    def provider(settings, bundle, **kwargs):
        received.append(bundle.public_payload())
        return {"report": "Тексерілген жауап", "local": False, "from_cache": False, "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr("moneymap.ui_ai.request_analysis", provider)
    app.radio(key="ai_mode").set_value("Сұрақ жазу").run()
    question = "Seed-тен 1008-ке жол"
    app.text_area(key="ai_question").set_value(question).run()
    app.button(key="ai_ask_question").click().run()
    assert not app.exception and not received
    assert app.session_state["ai_output"]["local"]
    app.button(key="ai_generate").click().run()
    assert not app.exception and len(received) == 1
    public = json.dumps(received[0], ensure_ascii=False)
    assert question not in public and "1008" not in public
    assert received[0]["task"] == "seed_paths"
    assert any(fact["source"] == "graph.seed_path" for fact in received[0]["facts"])







#