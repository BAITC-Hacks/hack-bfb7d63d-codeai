"""Invalidate map widgets and callbacks whenever their source results change."""

import streamlit as st


def clear_map_state():
    for key in list(st.session_state):
        if key.startswith("map_"):
            st.session_state.pop(key, None)
