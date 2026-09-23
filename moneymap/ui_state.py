"""Invalidate map widgets and callbacks whenever their source results change."""

import streamlit as st


def clear_ai_state():
    for key in list(st.session_state):
        if key.startswith("ai_"):
            st.session_state.pop(key, None)


def clear_map_state():
    for key in list(st.session_state):
        if key.startswith("map_"):
            st.session_state.pop(key, None)


def clear_investigation_state():
    """Remove briefs, route results and scenarios when their data changes."""
    for key in list(st.session_state):
        if key.startswith(("inv_", "anomaly_")):
            st.session_state.pop(key, None)


def clear_evaluation_state():
    """Review labels belong to source data, not to a role recomputation."""
    for key in list(st.session_state):
        if key.startswith("eval_"):
            st.session_state.pop(key, None)
