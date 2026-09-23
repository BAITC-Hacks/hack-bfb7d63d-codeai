"""Analyst review queue, communities, and explainable client decisions."""

import pandas as pd
import streamlit as st

from moneymap.graph import analyze_dataset
from moneymap.reports import role_export_files, role_export_zip
from moneymap.roles import classify_graph
from moneymap.ui_graph import integer, money, safe_identifiers
from moneymap.ui_state import clear_map_state, clear_ai_state, queue_map_navigation


ROLE_LABELS = {
    "coordinator": "Үйлестіруші белгісі", "distributor": "Таратушы",
    "consolidator": "Жинақтаушы", "transit": "Транзит",
    "terminal": "Бақыланған соңғы алушы", "peripheral": "Дерек жеткіліксіз / периферия",
}
PRIORITY_PARTS = {
    "priority_consolidation": "Жинақталу белгісі", "priority_in_kzt": "Кіріс көлемі",
    "priority_in_deg": "Жіберушілер саны", "priority_betweenness": "Байланыс жолдарындағы орны",
    "priority_seed_reach": "Бастапқы клиенттермен байланыс", "priority_out_deg": "Алушылар саны",
    "priority_pagerank": "Желідегі байланыс салмағы",
}


def ensure_role_analysis(validation):
    """Compute once for the current validated dataset; never reload source data."""
    if not validation.valid:
        return None
    result = st.session_state.get("role_analysis")
    if result is None:
        try:
            graph = st.session_state.get("analysis")
            if graph is None:
                graph = analyze_dataset(validation.frames)
                st.session_state.analysis = graph
            result = classify_graph(graph)
            st.session_state.role_analysis = result
        except Exception as exc:
            st.error("Талдау аяқталмады. Деректерді тексеріп, қайта іске қосыңыз.")
            with st.expander("Қате туралы мәлімет"):
                st.code(f"{type(exc).__name__}: {exc}")
            return None
    return result


def _prepare_roles(validation):
    if not validation.valid:
        st.info("Талдауды жалғастыру үшін деректердегі қателерді түзетіңіз.")
        return None
    if st.button("Рөлдер мен басымдықты есептеу", type="primary", key="compute_roles"):
        clear_map_state()
        clear_ai_state()
        for key in ("role_analysis", "role_gid", "role_cluster", "role_filter", "review_queue_table"):
            st.session_state.pop(key, None)
        with st.spinner("Байланыстар, рөлдер және тексеру кезегі есептеліп жатыр…"):
            ensure_role_analysis(validation)
    result = st.session_state.get("role_analysis")
    if result is None:
        st.info("Есептеуді бастаңыз. Құрал барлық клиентке рөл болжамын беріп, тексеру кезегін жасайды. API қажет емес.")
    return result


def _display_roles(frame):
    result = safe_identifiers(frame)
    if "role" in result:
        result["role"] = result.role.map(ROLE_LABELS).fillna(result.role)
    return result


def _queue_selected_row(gids):
    state = st.session_state.get("review_queue_table", {})
    rows = state.get("selection", {}).get("rows", [])
    if rows and 0 <= rows[0] < len(gids):
        queue_map_navigation(gid=gids[rows[0]], rerun=False)


def _render_queue(result):
    cols = st.columns(3)
    cols[0].metric("Тексеру кезегінде", integer(len(result.top_nodes)))
    cols[1].metric("Талдауға кірген клиент", integer(len(result.nodes_roles)))
    cols[2].metric("Байланыс топтары", integer(len(result.clusters)))
    st.caption("Клиент жолын таңдаңыз — оның байланыстары картада ашылады. Басымдық ұпайы кінәлілік ықтималдығын білдірмейді.")
    st.dataframe(_display_roles(result.top_nodes), hide_index=True, width="stretch",
        key="review_queue_table", selection_mode="single-row",
        on_select=lambda: _queue_selected_row([str(gid) for gid in result.top_nodes.gid]),
        column_config={
            "rank": st.column_config.NumberColumn("Кезек", width="small"),
            "gid": st.column_config.TextColumn("Клиент ID", width="medium"),
            "role": st.column_config.TextColumn("Рөл болжамы", width="medium"),
            "priority_score": st.column_config.ProgressColumn("Басымдық", min_value=0, max_value=1, format="%.3f"),
            "why": st.column_config.TextColumn("Тексеру негізі", width="large"),
        })
    st.subheader("Клиент бойынша негіздеме")
    gids = result.details.sort_values(["priority_score", "in_kzt", "gid"], ascending=[False, False, True]).gid
    pick, action = st.columns([3, 1], vertical_alignment="bottom")
    selected = pick.selectbox("Клиент ID", [str(gid) for gid in gids], index=None, placeholder="Толық ID арқылы іздеу", key="role_gid")
    if action.button("Желіде ашу →", key="queue_open_map", disabled=selected is None, width="stretch"):
        queue_map_navigation(gid=selected)
    if selected:
        with st.container(border=True):
            _render_role_detail(result, selected)


def _render_all_roles(result):
    counts = result.nodes_roles.role.value_counts().reindex(ROLE_LABELS, fill_value=0)
    chosen = st.selectbox("Рөл бойынша сүзу", ["all", *ROLE_LABELS], format_func=lambda role: "Барлық рөлдер" if role == "all" else f"{ROLE_LABELS[role]} · {counts[role]}", key="role_filter")
    nodes = result.nodes_roles if chosen == "all" else result.nodes_roles.loc[result.nodes_roles.role.eq(chosen)]
    st.caption(f"{integer(len(nodes))} клиент. Толық нәтижелер: «Деректер және экспорт» → «Экспорт».")
    st.dataframe(_display_roles(nodes), hide_index=True, width="stretch", column_config={
        "gid": st.column_config.TextColumn("Клиент ID"), "role": "Рөл болжамы",
        "role_score": st.column_config.NumberColumn("Ережеге сәйкестік", format="%.3f"),
        "priority_score": st.column_config.ProgressColumn("Басымдық", min_value=0, max_value=1, format="%.3f"),
        "cluster_id": "Топ", "evidence": "Негіздеме",
    })


def _render_clusters(result):
    st.caption("Топтар аударым байланыстары бойынша есептелген. Бір топқа кіру ұйымға мүшелікті дәлелдемейді.")
    st.dataframe(result.clusters, hide_index=True, width="stretch", column_config={
        "cluster_id": "Топ", "n_nodes": "Клиенттер", "n_seed": "Бастапқы клиенттер",
        "sum_kzt_internal": st.column_config.NumberColumn("Ішкі айналым, ₸", format="%.2f"),
        "top_gids": "Басым клиенттер", "hypothesis": st.column_config.TextColumn("Тексерілетін болжам", width="large"),
    })
    selector, action = st.columns([3, 1], vertical_alignment="bottom")
    cluster_id = selector.selectbox("Топты зерттеу", result.clusters.cluster_id.tolist(), format_func=lambda value: f"{value}-топ", key="role_cluster")
    if action.button("Картада ашу →", key="cluster_open_map", width="stretch"):
        queue_map_navigation(cluster_id=cluster_id)
    members = result.details.loc[result.details.cluster_id.eq(cluster_id)].sort_values(["priority_score", "gid"], ascending=[False, True])
    cluster = result.clusters.set_index("cluster_id").loc[cluster_id]
    with st.container(border=True):
        cols = st.columns(3)
        cols[0].metric("Клиенттер", integer(cluster.n_nodes))
        cols[1].metric("Бастапқы клиенттер", integer(cluster.n_seed))
        cols[2].metric("Ішкі айналым", money(cluster.sum_kzt_internal))
        st.info(cluster.hypothesis)
        flow = next((item for item in result.summary.get("cluster_flow_metrics", []) if item["cluster_id"] == cluster_id), None)
        if flow:
            flow_cols = st.columns(3)
            flow_cols[0].metric("Топтан тыс кіріс", money(flow["external_in_kzt"]))
            flow_cols[1].metric("Топтан тыс шығыс", money(flow["external_out_kzt"]))
            share = flow["internal_share_of_incident_turnover"]
            flow_cols[2].metric("Ішкі айналым үлесі", "—" if share is None else f"{share:.1%}")
            st.caption("Ішкі үлес = топ ішіндегі аударым / топпен байланысты бүкіл бақыланған айналым. Бұл шот қалдығы емес.")
            if flow.get("boundary_count"):
                st.caption(f"{integer(flow['boundary_count'])} клиент 4-қадам шекарасында: одан кейінгі шығыс толық көрінбейді.")
        st.dataframe(_display_roles(members[["gid", "role", "priority_score", "in_kzt", "out_kzt", "is_seed", "depth"]]), hide_index=True, width="stretch", column_config={
            "gid": st.column_config.TextColumn("Клиент ID"), "role": "Рөл болжамы",
            "priority_score": st.column_config.ProgressColumn("Басымдық", min_value=0, max_value=1, format="%.3f"),
            "in_kzt": st.column_config.NumberColumn("Кіріс, ₸", format="%.2f"),
            "out_kzt": st.column_config.NumberColumn("Шығыс, ₸", format="%.2f"),
            "is_seed": "Бастапқы клиент", "depth": "Қадам",
        })


def render_exports(result=None):
    result = result if result is not None else st.session_state.get("role_analysis")
    if result is None:
        st.info("Есептерді алу үшін тексеру кезегін есептеңіз.")
        return
    st.subheader("Талдау нәтижелері")
    st.caption("Клиент рөлдері, байланыс топтары, тексеру кезегі және есептеу ережелері.")
    files = role_export_files(result)
    st.download_button("Барлық нәтижені жүктеу · ZIP", role_export_zip(files), file_name="moneymap-results.zip", mime="application/zip", key="download_roles_zip", type="primary")
    columns = st.columns(2)
    for index, (name, payload) in enumerate(files.items()):
        columns[index % 2].download_button(name, payload, file_name=name, mime="application/json" if name.endswith(".json") else "text/csv", key=f"download_{name}", width="stretch")
    st.caption("Excel-ге импорттағанда клиент ID бағанын мәтін түрінде таңдаңыз: ұзын идентификатор өзгермеуі керек.")


def _render_rules(result):
    with st.expander("Есептеу әдісі және шектеулер"):
        st.markdown("""
        - **Үйлестіруші белгісі:** бірнеше жіберуші, алушы және бастапқы клиентпен байланыс; желі жолдарындағы маңызды орын.
        - **Таратушы:** көптеген бірегей алушыға ақша жібереді.
        - **Жинақтаушы:** бірнеше жіберушіден ақша алады, көрінетін шығыс үлесі төмен.
        - **Транзит:** кіріс пен шығыс сомалары жақын; уақыттық қайшылық болмауы керек. Нақты сол ақшаның өткенін дәлелдемейді.
        - **Бақыланған соңғы алушы:** кіріс бар, осы кезеңде шығыс байқалмаған. Бастапқы және 4-қадамдағы клиенттер кірмейді.
        - **Дерек жеткіліксіз / периферия:** ережелер орындалмаған немесе бақылау шектеулі. Бұл «қауіпсіз» деген белгі емес.
        """)
        st.write("Бірнеше ереже орындалса: үйлестіруші → таратушы → жинақтаушы → транзит → соңғы алушы реті қолданылады. 4-қадам мен оқшау клиенттің дерек шектеуі алдымен ескеріледі.")
        st.caption("Рөл ұпайы — ережеге сәйкестік. Басымдық — жеті белгі үлесінің қосындысы. Екеуі де кінәлілік ықтималдығы емес.")
        st.json(result.config, expanded=False)
        st.json(result.summary, expanded=False)


def render_sensitivity(result=None):
    """Expose local parameter sensitivity without presenting it as accuracy."""
    result = result if result is not None else st.session_state.get("role_analysis")
    sensitivity = result.summary.get("sensitivity") if result is not None else None
    if not sensitivity:
        return
    with st.expander("Ереже өзгерсе, нәтиже қаншалықты өзгереді?"):
        st.write("Жинақтаушы шегі мен топтастыру параметрін аздап өзгертіп салыстырамыз. Бұл сапа дәлдігі немесе кінәлілікті табу пайызы емес.")
        scenarios = sensitivity.get("scenarios", [])
        if scenarios:
            frame = pd.DataFrame(scenarios)
            frame["parameter"] = frame.parameter.replace({"consolidator_min_in_deg": "Жинақтаушыға керек жіберушілер", "louvain_resolution": "Топтастыру масштабы"})
            columns = [name for name in ("parameter", "value", "role_changes", "top_overlap", "top_count", "n_clusters", "multi_seed_clusters") if name in frame]
            st.dataframe(frame[columns], hide_index=True, width="stretch", column_config={
                "parameter": "Өзгерген ереже", "value": "Мән", "role_changes": "Рөлі өзгерген клиент",
                "top_overlap": "Топ тізімде сақталған", "top_count": "Тізім көлемі", "n_clusters": "Топ саны", "multi_seed_clusters": "Бірнеше бастапқы клиенті бар топ",
            })
        st.caption("Басымдық рөлден бөлек есептеледі. Сондықтан рөл өзгеріп, тексеру тізімі сол қалпында қалуы мүмкін.")


def render_queue_page(validation):
    if st.session_state.get("role_analysis") is not None:
        with st.expander("Талдауды қайта есептеу"):
            result = _prepare_roles(validation)
    else:
        result = _prepare_roles(validation)
    if result is None:
        return
    queue, all_roles = st.tabs(["Басым клиенттер", "Барлық клиенттер"])
    with queue:
        _render_queue(result)
    with all_roles:
        _render_all_roles(result)
    _render_rules(result)
    render_sensitivity(result)


def render_clusters_page(validation):
    if st.session_state.get("role_analysis") is not None:
        with st.expander("Талдауды қайта есептеу"):
            result = _prepare_roles(validation)
    else:
        result = _prepare_roles(validation)
    if result is not None:
        _render_clusters(result)
        render_sensitivity(result)


def render_roles_tab(validation):
    """Compatibility wrapper for callers that still use the combined workspace."""
    st.subheader("Рөлдер және тексеру басымдығы")
    result = _prepare_roles(validation)
    if result is None:
        return
    tabs = st.tabs(["Тексеру кезегі", "Барлық рөлдер", "Кластерлер", "CSV файлдары"])
    with tabs[0]:
        _render_queue(result)
    with tabs[1]:
        _render_all_roles(result)
    with tabs[2]:
        _render_clusters(result)
    with tabs[3]:
        render_exports(result)
    _render_rules(result)


def _render_role_detail(result, gid_text):
    row = result.details.set_index("gid").loc[int(gid_text)]
    st.markdown(f"**{ROLE_LABELS[row.role]}** · клиент `{gid_text}`")
    cols = st.columns(3)
    cols[0].metric("Ережеге сәйкестік", f"{row.role_score:.3f}")
    cols[1].metric("Тексеру басымдығы", f"{row.priority_score:.3f}")
    cols[2].metric("Байланыс тобы", integer(row.cluster_id))
    st.info(row.evidence)
    st.write(f"Кіріс: **{money(row.in_kzt)}** · шығыс: **{money(row.out_kzt)}**. Жіберушілер: **{integer(row.in_deg)}**, алушылар: **{integer(row.out_deg)}**, жететін өзге бастапқы клиент: **{integer(row.reachable_seed_count)}**.")
    rules = result.config["rules"]
    cutoff = result.summary["thresholds"]["coordinator_betweenness_cutoff"]
    gate_text = {
        "coordinator": f"Жіберушілер ≥{rules['coordinator_min_in_deg']}, алушылар ≥{rules['coordinator_min_out_deg']}, жететін бастапқы клиент ≥{rules['coordinator_min_seed_reach']}; оң аралық орталықтық ≥{cutoff:.8f}." if cutoff is not None else "Оң аралық орталықтық байқалмаған.",
        "distributor": f"Бақылау шекарасынан тыс емес клиенттің бірегей алушылары ≥{rules['distributor_min_out_deg']}.",
        "consolidator": f"Жіберушілер ≥{rules['consolidator_min_in_deg']}, көрінетін шығыс/кіріс ≤{rules['consolidator_max_ratio']}; бастапқы клиент емес, қадам <4.",
        "transit": f"Екі бағыт та бар, көрінетін шығыс/кіріс {rules['transit_min_ratio']}–{rules['transit_max_ratio']}; бастапқы клиент емес, қадам <4. Барлық шығыс кірістен ерте болған уақыттық қайшылық жоқ.",
        "terminal": "Көрінетін кіріс >0, шығыс байланысы 0; бастапқы клиент емес, қадам <4; жоғары тұрған ережелер орындалмаған.",
        "peripheral": "Бақылау шектеулі немесе басым рөлдердің ережелері орындалмаған. Қосымша дерек қажет болуы мүмкін.",
    }
    st.write("**Орындалған ереже:** " + gate_text[row.role])
    if row.truncated_by_depth:
        st.warning("4-қадам — бақылау шекарасы. Шығыстың жоқтығы соңғы алушы екенін білдірмейді.")
    if row.is_seed:
        st.warning("Бастапқы клиенттің кірісі толық емес: шығыс/кіріс қатынасы рөлге дәлел ретінде қолданылмайды.")
    if row.is_isolated:
        st.info("Бақыланған аударымдар жоқ. Клиент сақталды; басымдық 0, әрі қарай бағалау үшін қосымша дерек қажет.")
    if bool(row.get("temporal_contradiction", False)):
        st.warning("Уақыттық қайшылық: барлық көрінетін шығыс алғашқы кіріс күнінен бұрын жасалған. Осы кірістер транзит болды деп қорытынды жасауға болмайды.")
    elif row.get("temporal_order_status") == "same_day_order_unknown":
        st.caption("Кіріс пен шығыс бір күнге сәйкес келеді. Сағат дерегі жоқ: бір күн ішіндегі реттілік белгісіз.")
    with st.expander("Ұпайдың құрамы және қосымша көрсеткіштер"):
        ratio = "анықталмаған" if pd.isna(row.observed_flow_ratio) else f"{row.observed_flow_ratio:.4f}"
        st.caption(f"Қадам: {int(row.depth)} · шығыс/кіріс: {ratio} · аралық орталықтық: {row.betweenness:.8f} · PageRank: {row.pagerank:.8f}.")
        matches = str(row.matched_roles).split("|")
        if len(matches) > 1:
            st.write("Қатар орындалған ережелер: " + ", ".join(ROLE_LABELS.get(role, role) for role in matches))
        contributions = pd.DataFrame({"Белгі": list(PRIORITY_PARTS.values()), "Ұпайға қосқан үлесі": [float(row[name]) for name in PRIORITY_PARTS]})
        st.dataframe(contributions.sort_values("Ұпайға қосқан үлесі", ascending=False), hide_index=True, width="stretch", column_config={"Ұпайға қосқан үлесі": st.column_config.NumberColumn(format="%.4f")})
        st.caption("Жеті үлестің қосындысы — басымдық ұпайы. Рөл ұпайы бұл қосындыға кірмейді. Ұпай осы деректер жиынына қатысты, басқа аймен тікелей салыстырылмайды.")
