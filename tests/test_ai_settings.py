"""Offline configuration tests use invented secrets and temporary files only."""

from dataclasses import replace

import pytest

from moneymap.ai_settings import AIConfigError, AISettings, NVIDIA_MODEL, OPENAI_MODEL, load_settings


def test_defaults_disabled_missing_key_and_no_secret_repr(tmp_path):
    settings = load_settings("openai", tmp_path, {})
    assert settings.model == OPENAI_MODEL and settings.enabled is False and settings.ready is False
    assert settings.budget_usd == 1 and settings.max_requests == 20 and settings.max_total_tokens == 200_000
    keyed = replace(settings, api_key="fake-secret-for-test", enabled=True)
    assert keyed.ready and "fake-secret" not in repr(keyed)


def test_bom_quotes_comments_environment_precedence_and_provider_separation(tmp_path):
    (tmp_path / ".env").write_text('# local\nOPENAI_API_KEY="fake-file-key" # comment\nNVIDIA_API_KEY=\'fake-nvidia-key\'\nMONEYMAP_AI_ENABLED=true\nMONEYMAP_AI_BUDGET_USD=2 # local cap\n', encoding="utf-8-sig")
    settings = load_settings("openai", tmp_path, {"OPENAI_API_KEY": "fake-env-key", "MONEYMAP_AI_MAX_REQUESTS": "3"})
    assert settings.api_key == "fake-env-key" and settings.ready and settings.max_requests == 3 and settings.budget_usd == 2
    nvidia = load_settings("nvidia", tmp_path, {})
    assert nvidia.model == NVIDIA_MODEL and nvidia.api_key == "fake-nvidia-key"
    assert load_settings("openai", tmp_path, {"OPENAI_API_KEY": ""}).ready is False


def test_no_shell_or_environment_interpolation(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY='${OTHER_KEY}'\nMONEYMAP_AI_ENABLED=true\n", encoding="utf-8")
    assert load_settings("openai", tmp_path, {"OTHER_KEY": "do-not-expand"}).api_key == "${OTHER_KEY}"


@pytest.mark.parametrize("setting,value", [
    ("OPENAI_MODEL", "fake-secret-not-a-model"),
    ("MONEYMAP_AI_ENABLED", "fake-secret-not-a-boolean"),
    ("MONEYMAP_AI_BUDGET_USD", "NaN"), ("MONEYMAP_AI_BUDGET_USD", "51"),
    ("MONEYMAP_AI_MAX_REQUESTS", "0"), ("MONEYMAP_AI_MAX_TOTAL_TOKENS", "-1"),
    ("MONEYMAP_AI_MAX_OUTPUT_TOKENS", "9000"), ("MONEYMAP_AI_TIMEOUT_SECONDS", "999"),
    ("OPENAI_API_KEY", "fake-secret with newline\n"),
])
def test_invalid_settings_fail_without_echoing_values(tmp_path, setting, value):
    with pytest.raises(AIConfigError) as caught:
        load_settings("openai", tmp_path, {setting: value})
    assert "fake-secret" not in str(caught.value) and "fake-secret" not in repr(caught.value)


@pytest.mark.parametrize("text", ["SECRET-MATERIAL", "OPENAI_API_KEY='fake-secret", "bad name=fake-secret", 'OPENAI_API_KEY="fake-secret" unsupported'])
def test_invalid_dotenv_does_not_leak_its_line(tmp_path, text):
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    with pytest.raises(AIConfigError) as caught:
        load_settings("openai", tmp_path, {})
    assert text not in str(caught.value) and "fake-secret" not in str(caught.value)


def test_unknown_provider_and_model_rejected_even_when_constructed_directly():
    with pytest.raises(AIConfigError):
        AISettings("untrusted-host", OPENAI_MODEL, "")
    with pytest.raises(AIConfigError):
        AISettings("openai", "gpt-4.1-mini", "")


def test_no_parent_directory_dotenv_lookup(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=fake-parent-key\nMONEYMAP_AI_ENABLED=true\n", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    assert not load_settings("openai", child, {}).ready
