"""Analyst edits survive reruns but never migrate to different source data."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


HARNESS = '''
import streamlit as st
from moneymap.data import validate_dataset
from moneymap.demo import create_demo_frames
from moneymap.graph import analyze_dataset
from moneymap.roles import classify_graph
from moneymap.ui_evaluation import render_evaluation_tab
frames = create_demo_frames()
if st.session_state.get("alternate_dataset"):
    frames["transactions"].loc[0, "date"] = "2026-07-30"
validation = validate_dataset(frames)
if st.button("Болжамды қайта есептеу", key="rerun_predictions"):
    st.session_state.analysis = analyze_dataset(validation.frames)
    st.session_state.role_analysis = classify_graph(st.session_state.analysis)
if st.button("Деректерді ауыстыру", key="replace_dataset"):
    st.session_state.alternate_dataset = True
    st.session_state.pop("analysis", None)
    st.session_state.pop("role_analysis", None)
    st.rerun()
render_evaluation_tab(validation)
'''


def test_empty_state_manual_review_rerun_export_and_dataset_invalidation():
    app = AppTest.from_string(HARNESS, default_timeout=30).run()
    assert not app.exception
    assert not app.session_state["eval_reviews"]
    app.button(key="eval_prepare").click().run()
    assert not app.exception
    assert any("accuracy және F1 есептелген жоқ" in item.value for item in app.info)
    assert all(item.value == "—" for item in app.metric)
    gid = app.selectbox(key="eval_gid").value
    app.selectbox(key=f"eval_editor_role_{gid}").select("terminal")
    app.selectbox(key=f"eval_editor_relevance_{gid}").select("true")
    app.text_area(key=f"eval_editor_note_{gid}").set_value("Құжатпен тексерілді; бұл тек осы іріктеме.")
    app.button(key="eval_save").click().run()
    assert not app.exception
    stored = app.session_state["eval_reviews"][gid]
    assert stored.reviewed_role == "terminal" and stored.investigation_relevant == "true"
    assert any("1 / 16" in item.value for item in app.markdown)
    assert any("шағын іріктемеге" in item.value for item in app.warning)
    digest = app.session_state["eval_dataset_sha256"]
    app.button(key="rerun_predictions").click().run()
    assert not app.exception
    assert app.session_state["eval_reviews"][gid] == stored
    app.selectbox(key="eval_gid").select("1004").run()
    app.selectbox(key="eval_gid").select(gid).run()
    assert app.selectbox(key=f"eval_editor_role_{gid}").value == "terminal"
    assert app.text_area(key=f"eval_editor_note_{gid}").value == stored.reviewer_note
    app.button(key="replace_dataset").click().run()
    assert not app.exception
    assert app.session_state["eval_dataset_sha256"] != digest
    assert not app.session_state["eval_reviews"]
    assert "eval_ready" not in app.session_state


def test_unknown_save_is_not_counted_as_reviewed_role_or_relevant_negative():
    app = AppTest.from_string(HARNESS, default_timeout=30).run()
    app.button(key="eval_prepare").click().run()
    app.button(key="eval_save").click().run()
    assert not app.exception
    assert len(app.session_state["eval_reviews"]) == 1
    assert all(item.value == "—" for item in app.metric)
    assert any("0 / 16" in item.value for item in app.markdown)
    app.button(key="eval_import").click().run()
    assert any("Алдымен толтырылған CSV" in item.value for item in app.info)


def test_actual_app_same_dataset_recheck_preserves_expert_review_and_rerenders():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    app.button(key="eval_prepare").click().run()
    assert not app.exception
    gid = app.selectbox(key="eval_gid").value
    app.selectbox(key=f"eval_editor_role_{gid}").select("terminal")
    app.selectbox(key=f"eval_editor_relevance_{gid}").select("true")
    app.text_area(key=f"eval_editor_note_{gid}").set_value("Бір деректі қайта тексергенде сақталуы тиіс.")
    app.button(key="eval_save").click().run()
    review = app.session_state["eval_reviews"][gid]
    fingerprint = app.session_state["eval_dataset_sha256"]

    # Revalidating the same source refreshes computed reports, not human labels.
    next(button for button in app.button if button.label == "Демо деректермен тексеру").click().run()
    assert not app.exception
    assert app.session_state["eval_dataset_sha256"] == fingerprint
    assert app.session_state["eval_reviews"] == {gid: review}
    app.button(key="eval_prepare").click().run()
    assert not app.exception
    app.selectbox(key="eval_gid").select(gid).run()
    assert app.selectbox(key=f"eval_editor_role_{gid}").value == "terminal"
    assert app.selectbox(key=f"eval_editor_relevance_{gid}").value == "true"
    assert app.text_area(key=f"eval_editor_note_{gid}").value == review.reviewer_note
    assert any("1 / 16" in item.value for item in app.markdown)
    app.run()
    assert not app.exception
    assert app.session_state["eval_reviews"] == {gid: review}
