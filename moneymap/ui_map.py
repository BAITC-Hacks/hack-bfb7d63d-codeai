"""Directed interactive map and full client card backed only by local data."""

import hashlib
import json
import math
from uuid import uuid4

import pandas as pd
import streamlit as st

from moneymap.data import _exact_integer
from moneymap.graph import analyze_dataset, observed_seed_paths
from moneymap.graph_view import build_graph_view, client_neighbors, client_transactions
from moneymap.map_component import render_network, selected_from_event
from moneymap.roles import classify_graph
from moneymap.ui_graph import integer, safe_identifiers
from moneymap.ui_roles import ROLE_LABELS, _render_role_detail
from moneymap.ui_state import clear_map_state


def render_map_tab(validation):
    apply_pending_map_navigation()
    st.subheader("Желі картасы")
    st.write("Клиентті тауып, ақшаның кімнен келіп, кімге кеткенін зерттеңіз. Көрсеткі жіберушіден алушыға бағытталған.")
    if not validation.valid:
        st.info("Картаны ашу үшін алдымен деректердегі қателерді түзетіңіз.")
        return
    if st.button("Картаны дайындау", key="prepare_map", type="primary"):
        clear_map_state()
        with st.spinner("Карта үшін граф пен рөлдер дайындалып жатыр…"):
            try:
                graph = st.session_state.get("analysis")
                if graph is None:
                    graph = analyze_dataset(validation.frames)
                    st.session_state.analysis = graph
                roles = st.session_state.get("role_analysis")
                if roles is None:
                    roles = classify_graph(graph)
                    st.session_state.role_analysis = roles
                st.session_state.map_ready = True
                st.session_state.map_epoch = uuid4().hex
                gid = str(int(roles.top_nodes.loc[0, "gid"]))
                st.session_state.map_focus_gid = gid
                st.session_state.map_selected_gid = gid
            except Exception as exc:
                st.error("Картаны дайындау аяқталмады.")
                with st.expander("Қате туралы мәлімет"):
                    st.code(f"{type(exc).__name__}: {exc}")
    if not st.session_state.get("map_ready"):
        st.info("«Картаны дайындау» батырмасы қажет граф пен рөлдерді есептеп, басымдығы жоғары клиенттің айналасын ашады.")
        return

    graph = st.session_state.analysis
    roles = st.session_state.role_analysis
    with st.form("map_search_form", border=False):
        search, action = st.columns([3, 1])
        text = search.text_input("Кез келген клиентті іздеу · gid", key="map_search", placeholder="Толық gid енгізіңіз")
        submitted = action.form_submit_button("Картадан табу", width="stretch")
    if submitted:
        try:
            found = _exact_integer(text)
            if found not in graph.graph:
                raise ValueError("unknown gid")
            st.session_state.map_focus_gid = str(found)
            st.session_state.map_selected_gid = str(found)
            # Searching always opens the requested client, even after a strict filter.
            st.session_state.map_mode = "ego"
            st.session_state.map_role_filters = []
            st.session_state.map_cluster_filter = 0
        except (ValueError, TypeError, OverflowError):
            st.error("Бұл gid табылмады. Толық бүтін идентификаторды тексеріңіз; қазіргі карта сақталды.")

    controls = st.columns([2, 1, 1])
    mode = controls[0].selectbox("Карта ауқымы", ["ego", "full", "cluster"], format_func={"ego": "Клиенттің айналасы", "full": "Толық желі", "cluster": "Бір кластер"}.get, key="map_mode")
    hops = controls[1].selectbox("Қадам саны", [1, 2], disabled=mode != "ego", key="map_hops")
    direction = controls[2].selectbox("Жол бағыты", ["both", "incoming", "outgoing"], format_func={"both": "Екі бағыт", "incoming": "Клиентке қарай", "outgoing": "Клиенттен әрі"}.get, disabled=mode != "ego", key="map_direction")
    filters = st.columns([2, 1, 1])
    selected_roles = filters[0].multiselect("Картадағы рөлдер", list(ROLE_LABELS), format_func=ROLE_LABELS.get, key="map_role_filters", placeholder="Барлық рөл")
    cluster = filters[1].selectbox("Картадағы кластер", [0, *roles.clusters.cluster_id.tolist()], format_func=lambda value: "Барлығы" if value == 0 else f"Кластер {value}", key="map_cluster_filter")
    color = filters[2].selectbox("Түспен белгілеу", ["role", "cluster", "depth"], format_func={"role": "Рөл", "cluster": "Кластер", "depth": "Буын"}.get, key="map_color")
    amount_col, focus_col = st.columns([2, 1])
    minimum = amount_col.number_input("Байланыстың ең аз жиынтық сомасы, ₸", min_value=0.0, value=0.0, step=5000.0, key="map_min_amount")
    if focus_col.button("Таңдалған клиенттің айналасы", key="map_recenter", width="stretch"):
        st.session_state.map_focus_gid = st.session_state.map_selected_gid
        # The mode widget is already instantiated: use a pending update before rerun.
        st.session_state.map_pending_ego = True
        st.rerun()
    effective_cluster = cluster or None
    if mode == "cluster" and effective_cluster is None:
        effective_cluster = int(roles.details.set_index("gid").loc[int(st.session_state.map_focus_gid), "cluster_id"])
        st.caption(f"Кластер таңдалмады: карта ортасындағы клиенттің {effective_cluster}-кластері көрсетіледі.")
    payload = build_graph_view(
        graph, roles, focus_gid=st.session_state.map_focus_gid, mode=mode,
        hops=hops, direction=direction, role_filter=selected_roles or None,
        cluster_filter=effective_cluster, min_amount=minimum, color_by=color,
    )
    visible = {node["id"] for node in payload["nodes"]}
    if st.session_state.map_selected_gid not in visible:
        st.session_state.map_selected_gid = st.session_state.map_focus_gid
    payload["selected_gid"] = st.session_state.map_selected_gid
    signature = {
        "epoch": st.session_state.map_epoch, "focus": st.session_state.map_focus_gid,
        "mode": mode, "hops": hops, "direction": direction, "roles": sorted(selected_roles),
        "cluster": effective_cluster, "amount": minimum, "color": color,
    }
    view_key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode("utf-8")).hexdigest()
    summary = payload["summary"]
    st.session_state.map_summary = summary
    st.caption(f"Көрсетілгені: {integer(summary['visible_nodes'])} клиент, {integer(summary['visible_edges'])} бағытталған байланыс. Жалпы жиын: {integer(summary['total_nodes'])} клиент, {integer(summary['total_edges'])} байланыс.")
    if summary["excluded_nodes"] or summary["excluded_edges"]:
        st.caption(f"Осы ауқымда сүзгі жасырғаны: {integer(summary['excluded_nodes'])} клиент, {integer(summary['excluded_edges'])} байланыс. Есептелген рөлдер мен ұпайлар өзгерген жоқ.")
    if summary["focus_outside_filter"]:
        st.warning("Карта ортасындағы клиент сүзгіге сәйкес келмесе де, іздеуде жоғалмауы үшін көрсетілді.")
    if mode == "ego":
        st.caption("Қадам саны клиенттерді таңдайды; олардың арасындағы барлық жарамды бағытталған байланыс көрсетіледі. Бұл уақыт бойынша дәл сол ақшаның жүрген жолы дегенді білдірмейді.")

    event = render_network(payload, view_key, widget_key=f"map_canvas_{st.session_state.map_epoch}")
    selected = selected_from_event(event, view_key, visible, st.session_state.get("map_last_nonce"))
    if selected is not None:
        st.session_state.map_selected_gid = selected
        st.session_state.map_last_nonce = event["nonce"]
        # A component event reruns Python with the previous render arguments.
        # Confirm the new selection to the browser; nonce prevents a loop.
        st.rerun()
    st.caption("Клиентті картадан бассаңыз, төмендегі карточка ашылады. Ромб — seed, үзік жиек — 4-буын. Өлшем — басымдық, сызық ені — бақыланған сома.")
    _render_client_card(validation.frames, graph, roles, st.session_state.map_selected_gid)


def apply_pending_map_navigation():
    """Apply navigation before selectbox widgets are constructed on the rerun."""
    if st.session_state.pop("map_pending_ego", False):
        st.session_state.map_mode = "ego"
        st.session_state.map_role_filters = []
        st.session_state.map_cluster_filter = 0


def _json_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _render_client_card(frames, graph, roles, gid):
    st.divider()
    st.subheader(f"Клиент карточкасы · {gid}")
    st.caption("Карточка бүкіл бақыланған кезеңнің деректерін көрсетеді. Карта сүзгісі кіріс/шығысқа, рөлге немесе операциялар тізіміне әсер етпейді.")
    row = roles.details.set_index("gid").loc[int(gid)]
    tabs = st.tabs(["Рөл және көрсеткіштер", "Тікелей байланыстар", "Жеке операциялар", "Seed жолдары"])
    with tabs[0]:
        _render_role_detail(roles, gid)
        cols = st.columns(3)
        cols[0].metric("Кіріс операциялары", integer(row.in_tx))
        cols[1].metric("Шығыс операциялары", integer(row.out_tx))
        cols[2].metric("Белсенді күндер", integer(row.active_days))
        if pd.notna(row.first_date):
            st.caption(f"Кезең: {row.first_date:%Y-%m-%d} — {row.last_date:%Y-%m-%d}.")
        share = "дерек жеткіліксіз" if pd.isna(row.next_out_1_2d_share) else f"{row.next_out_1_2d_share:.1%}"
        st.write(f"Кейінгі 1–2 күнде шығыс байқалған кірістер үлесі: **{share}**; есепке кіргені — {integer(row.temporal_eligible_in_tx)} операция.")
        st.caption("Соңғы екі күндегі кірістер үлеске кірмейді. Бір күн ішіндегі реттілік пен қаражаттың сәйкестігі анықталмайды.")
        card = {"gid": gid, "metrics": {key: _json_value(value) for key, value in row.items()}, "observation_period": {"from": graph.summary.get("min_date"), "to": graph.summary.get("max_date")}, "limitations": "Only supplied observed transfers are included. Roles are hypotheses; seed incoming and depth-4 outgoing are incomplete."}
        st.download_button("Клиент карточкасын жүктеу · JSON", json.dumps(card, ensure_ascii=False, indent=2, allow_nan=False), file_name=f"client-{gid}.json", mime="application/json", key="map_download_card")
    with tabs[1]:
        neighbors = client_neighbors(graph, roles, gid)
        if neighbors.empty:
            st.info("Бақыланған тікелей байланыс жоқ. Клиент картада сақталған.")
        else:
            st.dataframe(safe_identifiers(neighbors), hide_index=True, width="stretch", column_config={
                "src": "Жіберуші gid", "dst": "Алушы gid", "counterparty_gid": "Қарсы тарап gid", "direction_label": "Бағыт",
                "sum_kzt": st.column_config.NumberColumn("Сома, ₸", format="%.2f"), "n_tx": "Операциялар", "role": "Қарсы тарап рөлі", "cluster_id": "Кластер",
            })
            st.download_button("Байланыстарды жүктеу · CSV", neighbors.to_csv(index=False).encode("utf-8-sig"), file_name=f"client-{gid}-neighbors.csv", mime="text/csv", key="map_download_neighbors")
    with tabs[2]:
        transactions = client_transactions(frames, gid)
        st.caption(f"{integer(len(transactions))} операция. Бірдей күн, сома және қатысушыларымен қайталанған жолдар сақталған.")
        if transactions.empty:
            st.info("Осы клиентке қатысты операция жоқ.")
        else:
            st.dataframe(safe_identifiers(transactions), hide_index=True, width="stretch", column_config={
                "src": "Жіберуші gid", "dst": "Алушы gid", "date": "Күн", "direction_label": "Бағыт",
                "sum_kzt": st.column_config.NumberColumn("Сома, ₸", format="%.2f"),
            })
            st.download_button("Операцияларды жүктеу · CSV", transactions.to_csv(index=False).encode("utf-8-sig"), file_name=f"client-{gid}-transactions.csv", mime="text/csv", key="map_download_transactions")
    with tabs[3]:
        paths = observed_seed_paths(graph, gid, limit=5)
        if not paths:
            st.info("Өзге бастапқы клиенттен бағытталған жол табылмады.")
        for path in paths:
            st.code(" → ".join(str(node) for node in path), language=None)
        st.caption("Ең көбі бес қысқа құрылымдық жол. Аударымдардың хронологиясы немесе дәл сол ақшаның қозғалысы бұл жолдармен дәлелденбейді.")
