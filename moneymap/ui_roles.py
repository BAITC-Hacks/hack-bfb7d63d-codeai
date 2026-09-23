"""Reviewable role hypotheses, cluster summaries and investigation priorities."""

import pandas as pd
import streamlit as st

from moneymap.graph import analyze_dataset
from moneymap.reports import role_export_files, role_export_zip
from moneymap.roles import classify_graph
from moneymap.ui_graph import integer, money, safe_identifiers
from moneymap.ui_state import clear_map_state


ROLE_LABELS = {
    "coordinator": "Үйлестіруші белгісі",
    "distributor": "Таратушы",
    "consolidator": "Жинақтаушы",
    "transit": "Транзит",
    "terminal": "Бақыланған соңғы алушы",
    "peripheral": "Периферия / дерек жеткіліксіз",
}
PRIORITY_PARTS = {
    "priority_consolidation": "Жинақталу белгісі",
    "priority_in_kzt": "Кіріс көлемі",
    "priority_in_deg": "Жіберушілер саны",
    "priority_betweenness": "Жолдардағы аралық орын",
    "priority_seed_reach": "Seed-ден жету",
    "priority_out_deg": "Алушылар саны",
    "priority_pagerank": "PageRank",
}


def render_roles_tab(validation):
    st.subheader("Рөлдер және тексеру басымдығы")
    st.write("Алдымен қай клиентті қарау керек және неге? Ережелерге сүйенген болжам, кластерлер және түсіндірмесі бар кезек.")
    if not validation.valid:
        st.info("Алдымен деректердегі қателерді түзетіңіз. Жарамсыз жиынға рөлдер есептелмейді.")
        return
    if st.button("Рөлдер мен басымдықты есептеу", type="primary", key="compute_roles"):
        clear_map_state()
        for key in ("role_analysis", "role_gid", "role_cluster"):
            st.session_state.pop(key, None)
        with st.spinner("Граф, кластерлер, рөлдер және тексеру кезегі есептеліп жатыр…"):
            try:
                graph = st.session_state.get("analysis")
                if graph is None:
                    graph = analyze_dataset(validation.frames)
                    st.session_state.analysis = graph
                st.session_state.role_analysis = classify_graph(graph)
            except Exception as exc:
                st.error("Рөлдерді есептеу аяқталмады. Төмендегі қатені қарап, қайта есептеңіз.")
                with st.expander("Қате туралы мәлімет"):
                    st.code(f"{type(exc).__name__}: {exc}")
    result = st.session_state.get("role_analysis")
    if result is None:
        st.info("Батырма графтан бастап рөлдерге дейін есептейді. API кілті қажет емес.")
        return

    st.success(f"{integer(len(result.nodes_roles))} клиентке рөл берілді · {integer(len(result.clusters))} кластер · топ-{len(result.top_nodes)} дайын")
    st.caption("Рөл — тексеруге арналған болжам. Рөл ұпайы ережеге сәйкестікті, басымдық ұпайы тексеру кезегін көрсетеді; екеуі де кінәлілік ықтималдығы емес.")
    tabs = st.tabs(["Тексеру кезегі", "Барлық рөлдер", "Кластерлер", "CSV файлдары"])
    with tabs[0]:
        st.dataframe(safe_identifiers(result.top_nodes), hide_index=True, width="stretch", column_config={
            "rank": "Кезек", "gid": st.column_config.TextColumn("gid"),
            "role": "Рөл коды", "priority_score": st.column_config.NumberColumn("Басымдық", format="%.3f"), "why": "Неге тексеру керек",
        })
        st.caption("Жоғары ұпай — осы үзіндідегі құрылымдық белгілер бойынша ертерек қарау ұсынысы. Тізім барлық клиенттің ішінен есептеледі.")
        gids = result.details.sort_values(["priority_score", "in_kzt", "gid"], ascending=[False, False, True]).gid
        selected = st.selectbox("Рөлдің негізін қарау · gid", [str(gid) for gid in gids], index=None, placeholder="Кез келген клиенттің gid мәнін енгізіңіз", key="role_gid")
        if selected:
            _render_role_detail(result, selected)
    with tabs[1]:
        counts = result.nodes_roles.role.value_counts().reindex(ROLE_LABELS, fill_value=0)
        st.dataframe(pd.DataFrame({"Рөл": [ROLE_LABELS[role] for role in counts.index], "Клиенттер": counts.values}), hide_index=True, width="stretch")
        chosen = st.selectbox("Рөл бойынша сүзу", ["all", *ROLE_LABELS], format_func=lambda role: "Барлығы" if role == "all" else ROLE_LABELS[role], key="role_filter")
        nodes = result.nodes_roles
        if chosen != "all":
            nodes = nodes.loc[nodes.role.eq(chosen)]
        st.caption(f"{integer(len(nodes))} клиент · барлық жолды CSV арқылы алуға болады.")
        st.dataframe(safe_identifiers(nodes), hide_index=True, width="stretch", column_config={
            "gid": st.column_config.TextColumn("gid"), "role": "Рөл коды",
            "role_score": st.column_config.NumberColumn("Рөл ұпайы", format="%.3f"),
            "priority_score": st.column_config.NumberColumn("Басымдық", format="%.3f"),
            "cluster_id": "Кластер", "evidence": "Рөлдің негізі",
        })
    with tabs[2]:
        st.write("Louvain байланысы тығыз топтарды табады. Бір үлкен байланысқан бөліктің ішінде бірнеше кластер болуы мүмкін. Бұл топтар ұйымға мүшелікті дәлелдемейді.")
        st.dataframe(result.clusters, hide_index=True, width="stretch", column_config={
            "cluster_id": "Кластер", "n_nodes": "Клиенттер", "n_seed": "Seed",
            "sum_kzt_internal": st.column_config.NumberColumn("Ішкі айналым, ₸", format="%.2f"),
            "top_gids": "Басым клиенттер", "hypothesis": "Тексерілетін болжам",
        })
        cluster_id = st.selectbox("Кластердің клиенттері", result.clusters.cluster_id.tolist(), format_func=lambda value: f"Кластер {value}", key="role_cluster")
        members = result.details.loc[result.details.cluster_id.eq(cluster_id)].sort_values(["priority_score", "gid"], ascending=[False, True])
        hypothesis = result.clusters.set_index("cluster_id").loc[cluster_id, "hypothesis"]
        st.info(hypothesis)
        st.dataframe(safe_identifiers(members[["gid", "role", "priority_score", "in_kzt", "out_kzt", "is_seed", "depth"]]), hide_index=True, width="stretch")
    with tabs[3]:
        st.write("ТЗ талап еткен үш CSV және есептеу ережелері сақталған JSON есебі дайын.")
        files = role_export_files(result)
        st.download_button("Барлық нәтижені жүктеу · ZIP", role_export_zip(files), file_name="moneymap-stage3.zip", mime="application/zip", key="download_roles_zip")
        for name, payload in files.items():
            st.download_button(name, payload, file_name=name, mime="application/json" if name.endswith(".json") else "text/csv", key=f"download_{name}")
        st.caption("Excel-ге импорттағанда gid бағанын мәтін ретінде таңдаңыз. top_gids — дәл идентификаторлары бар JSON мәтін тізімі.")

    with st.expander("Рөлдер мен басымдықтың ережелері"):
        st.markdown("""
        - **Үйлестіруші белгісі:** бірнеше бағыттағы байланыс, бірнеше seed-ден жету және жоғары аралық орталықтық қатар байқалады.
        - **Таратушы:** көптеген бірегей алушыға шығыс бар.
        - **Жинақтаушы:** бірнеше жіберушіден кіріс бар, көрінетін шығыс/кіріс қатынасы төмен.
        - **Транзит:** көрінетін кіріс пен шығыс сомалары жақын. Бұл дәл сол ақша өткенінің дәлелі емес.
        - **Бақыланған соңғы алушы:** кіріс бар, шығыс осы кезеңде байқалмаған; seed пен 4-буын бұған кірмейді.
        - **Периферия / дерек жеткіліксіз:** жоғарыдағы ережелер орындалмаған немесе бақылау шектеулі. Бұл «қауіпсіз» деген белгі емес.
        """)
        st.write("Бірнеше ереже орындалса: үйлестіруші → таратушы → жинақтаушы → транзит → соңғы алушы ретімен негізгі рөл таңдалады. 4-буын және оқшау түйін алдымен шектеулі дерек ретінде белгіленеді.")
        st.write("Басымдық рөл атауынан бөлек есептеледі: жинақталу, кіріс көлемі, жіберушілер саны, аралық орталықтық, seed-ден жету, алушылар саны және PageRank үлестері қосылады.")
        st.json(result.config, expanded=False)
        st.json(result.summary, expanded=False)


def _render_role_detail(result, gid_text):
    row = result.details.set_index("gid").loc[int(gid_text)]
    st.markdown(f"**{gid_text} · {ROLE_LABELS[row.role]}**")
    cols = st.columns(3)
    cols[0].metric("Рөл ұпайы", f"{row.role_score:.3f}")
    cols[1].metric("Тексеру басымдығы", f"{row.priority_score:.3f}")
    cols[2].metric("Кластер", integer(row.cluster_id))
    st.info(row.evidence)
    st.write(f"Кіріс: **{money(row.in_kzt)}** · шығыс: **{money(row.out_kzt)}**. Жіберушілер: **{integer(row.in_deg)}**, алушылар: **{integer(row.out_deg)}**, жететін өзге seed: **{integer(row.reachable_seed_count)}**.")
    ratio = "анықталмаған" if pd.isna(row.observed_flow_ratio) else f"{row.observed_flow_ratio:.4f}"
    st.caption(f"Буын: {int(row.depth)} · көрінетін шығыс/кіріс: {ratio} · аралық орталықтық: {row.betweenness:.8f} · PageRank: {row.pagerank:.8f}.")
    rules = result.config["rules"]
    cutoff = result.summary["thresholds"]["coordinator_betweenness_cutoff"]
    gate_text = {
        "coordinator": f"Жіберушілер ≥{rules['coordinator_min_in_deg']}, алушылар ≥{rules['coordinator_min_out_deg']}, жететін seed ≥{rules['coordinator_min_seed_reach']}; оң аралық орталықтық ≥{cutoff:.8f}." if cutoff is not None else "Оң аралық орталықтық байқалмаған.",
        "distributor": f"Бақылау шекарасынан тыс емес клиенттің бірегей алушылары ≥{rules['distributor_min_out_deg']}.",
        "consolidator": f"Жіберушілер ≥{rules['consolidator_min_in_deg']}, көрінетін шығыс/кіріс ≤{rules['consolidator_max_ratio']}; seed емес, буын <4.",
        "transit": f"Екі бағыт та бар, көрінетін шығыс/кіріс {rules['transit_min_ratio']}–{rules['transit_max_ratio']} аралығында; seed емес, буын <4.",
        "terminal": "Көрінетін кіріс >0, шығыс байланысы 0; seed емес, буын <4; жоғары тұрған ережелер орындалмаған.",
        "peripheral": "Бақылау шектеулі немесе басым рөлдердің ережелері орындалмаған. Қосымша дерек қажет болуы мүмкін.",
    }
    st.write("**Орындалған ереже:** " + gate_text[row.role])
    matches = str(row.matched_roles).split("|")
    if len(matches) > 1:
        st.caption("Қатар орындалған ережелер: " + ", ".join(ROLE_LABELS.get(role, role) for role in matches))
    if row.truncated_by_depth:
        st.warning("4-буын — бақылау шекарасы. Шығыстың жоқтығы соңғы алушы екенін білдірмейді.")
    if row.is_seed:
        st.warning("Seed кірісі толық емес: шығыс/кіріс қатынасы рөлге дәлел ретінде қолданылмайды.")
    if row.is_isolated:
        st.info("Бақыланған аударымдар жоқ. Клиент сақталды; басымдық 0, әрі қарай бағалау үшін қосымша дерек қажет.")
    contributions = pd.DataFrame({"Белгі": list(PRIORITY_PARTS.values()), "Ұпайға қосқан үлесі": [float(row[name]) for name in PRIORITY_PARTS]})
    st.markdown("**Басымдық ұпайы неден құралды?**")
    st.dataframe(contributions.sort_values("Ұпайға қосқан үлесі", ascending=False), hide_index=True, width="stretch", column_config={"Ұпайға қосқан үлесі": st.column_config.NumberColumn(format="%.4f")})
    st.caption("Үлестердің қосындысы — басымдық ұпайы. Рөл ұпайы бұл қосындыға кірмейді. Ұпайлар осы деректер жиынына қатысты; басқа аймен тікелей салыстыруға арналмаған.")
