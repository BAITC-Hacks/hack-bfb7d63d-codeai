"""Invalidate map widgets and callbacks whenever their source results change."""

import streamlit as st

from moneymap.data import _exact_integer


def clear_ai_state():
    for key in list(st.session_state):
        if key.startswith("ai_"):
            st.session_state.pop(key, None)


def clear_map_state():
    for key in list(st.session_state):
        if key.startswith("map_"):
            st.session_state.pop(key, None)


def queue_map_navigation(*, gid=None, cluster_id=None, rerun=True):
    """Queue a map target without changing already-rendered widget values.

    Navigation callbacks set only pending state. The root consumes the page
    before its radio widget; the map consumes its target before map widgets.
    Dataset, graph and role results remain intact.
    """
    if (gid is None) == (cluster_id is None):
        raise ValueError("Choose exactly one client or cluster")
    request = {"mode": "ego" if gid is not None else "cluster"}
    if gid is not None:
        request["gid"] = str(_exact_integer(gid))
    else:
        request["cluster_id"] = _exact_integer(cluster_id)
    st.session_state.map_pending_navigation = request
    st.session_state.pending_workspace_page = "Желі картасы"
    if rerun:
        st.rerun()
