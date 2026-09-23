"""Local Streamlit bridge; client-selected IDs are never trusted as numbers."""

from pathlib import Path

from streamlit.components.v1 import declare_component


_network_component = declare_component("network_map", path=Path(__file__).resolve().parent / "graph_component")


def render_network(payload, view_key, widget_key):
    return _network_component(payload=payload, view_key=view_key, height=730, default=None, key=widget_key)


def selected_from_event(event, view_key, visible_ids, last_nonce=None):
    """Ignore stale, repeated or malformed browser messages and unknown IDs."""
    if not isinstance(event, dict) or event.get("view_key") != view_key:
        return None
    nonce = event.get("nonce")
    gid = event.get("gid")
    if not isinstance(nonce, str) or not 1 <= len(nonce) <= 128 or nonce == last_nonce:
        return None
    if not isinstance(gid, str) or gid not in visible_ids:
        return None
    return gid
