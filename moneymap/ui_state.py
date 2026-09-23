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
