"""Exercise tab inputs, stale-result handling, exact IDs and local execution."""

from streamlit.testing.v1 import AppTest


APP = '''
import streamlit as st
from moneymap.data import validate_dataset
from moneymap.demo import create_demo_frames
from moneymap.ui_anomalies import render_anomalies_tab
frames = st.session_state.get("test_frames", create_demo_frames())
render_anomalies_tab(validate_dataset(frames))
'''


def test_standalone_tab_recomputes_parameters_and_hides_stale_results():
    app = AppTest.from_string(APP, default_timeout=30).run()
    app.button(key="anomaly_compute").click().run()
    assert not app.exception
    assert app.session_state["anomaly_result"].summary["n_nodes"] == 16
    assert app.session_state["anomaly_result"].summary["alerts_detected"] == 0
    assert "analysis" not in app.session_state  # no mutation of shared graph/role results
    app.number_input(key="anomaly_sync_min").set_value(2).run()
    assert any("Параметрлер өзгерді" in item.value for item in app.info)
    assert not app.success
    app.button(key="anomaly_compute").click().run()
    assert not app.exception
    assert app.session_state["anomaly_result_params"]["sync_min_payers"] == 2
    assert app.session_state["anomaly_result"].summary["alerts_detected"] > 0
    app.selectbox(key="anomaly_signal_filter").select("same_day_payers").run()
    assert not app.exception
    assert any("Салыстырылған көрсеткіш" in item.value for item in app.markdown)


def test_source_change_invalidates_results_and_stale_shared_graph_is_not_reused():
    from moneymap.demo import create_demo_frames
    from moneymap.graph import analyze_dataset

    app = AppTest.from_string(APP, default_timeout=30).run()
    app.button(key="anomaly_compute").click().run()
    old_signature = app.session_state["anomaly_result_signature"]
    frames = create_demo_frames()
    app.session_state["analysis"] = analyze_dataset(frames)
    large = 9223372036854775700
    mapping = {gid: gid + large - 1001 for gid in frames["nodes"].gid}
    for name, columns in (("nodes", ["gid"]), ("edges", ["src", "dst"]), ("transactions", ["src", "dst"])):
        for column in columns:
            frames[name][column] = frames[name][column].map(mapping).astype("int64")
    # Use a large but safely int64 base for the 16-node synthetic dataset.
    app.session_state["test_frames"] = frames
    app.run()
    assert not app.exception
    assert "anomaly_result" not in app.session_state
    app.number_input(key="anomaly_sync_min").set_value(2).run()
    app.button(key="anomaly_compute").click().run()
    assert not app.exception
    assert old_signature != app.session_state["anomaly_result_signature"]
    assert all(isinstance(gid, str) and int(gid) > 2**53 for gid in app.session_state["anomaly_result"].alerts.gid)
    assert app.session_state["analysis"].nodes.gid.min() == 1001


def test_invalid_dataset_clears_previous_result():
    from moneymap.demo import create_demo_frames

    app = AppTest.from_string(APP, default_timeout=30).run()
    app.button(key="anomaly_compute").click().run()
    frames = create_demo_frames()
    frames["transactions"].loc[0, "sum_kzt"] = -1
    app.session_state["test_frames"] = frames
    app.run()
    assert not app.exception
    assert "anomaly_result" not in app.session_state
    assert not app.button
    assert any("қателерді түзетіңіз" in item.value for item in app.info)
