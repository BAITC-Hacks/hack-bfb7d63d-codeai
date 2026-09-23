"""Streamlit working surface for locally computed Stage 2 metrics."""

import json

import pandas as pd
import streamlit as st

from moneymap.graph import analyze_dataset, observed_seed_paths
from moneymap.reports import analysis_summary
from moneymap.ui_state import clear_map_state, clear_ai_state, clear_investigation_state


def safe_identifiers(frame):
    """Browser numbers cannot represent the supplied 18-digit identifiers."""
    safe = frame.copy()
    for column in ("gid", "src", "dst", "counterparty_gid"):
        if column in safe.columns:
            safe[column] = safe[column].map(lambda value: str(int(value)) if pd.notna(value) else "")
    return safe


def integer(value):
    return "—" if value is None or pd.isna(value) else f"{int(value):,}".replace(",", " ")


def money(value):
    return "—" if value is None or pd.isna(value) else f"{value:,.2f} ₸".replace(",", " ")


def render_graph_tab(validation):
    if not validation.valid:
        st.info("Графты есептеу үшін алдымен деректердегі қателерді түзетіңіз.")
        return
    st.subheader("Граф және көрсеткіштер")
    st.write("Барлық клиенттердің бағытталған байланыстары, ақша ағыны және уақыттық белгілері.")
    if st.button("Граф көрсеткіштерін есептеу", type="primary", key="compute_graph"):
        clear_map_state()
        clear_ai_state()
        clear_investigation_state()
        for key in ("analysis", "role_analysis", "role_gid", "role_cluster"):
            st.session_state.pop(key, None)
        with st.spinner("Граф, бастапқы клиенттермен байланыстар және күндік көрсеткіштер есептеліп жатыр…"):
            try:
                st.session_state.analysis = analyze_dataset(validation.frames)
            except Exception as exc:
                st.error("Графты есептеу аяқталмады. Деректерді тексеріп, қайта іске қосыңыз.")
                with st.expander("Қате туралы мәлімет"):
                    st.code(f"{type(exc).__name__}: {exc}")
    analysis = st.session_state.get("analysis")
    if analysis is None:
        st.info("Деректер дайын. Есептеуді бастау үшін жоғарыдағы батырманы басыңыз.")
        return

    st.success(f"Граф есептелді · {analysis.elapsed_seconds:.2f} секунд · {len(analysis.nodes):,} клиент сақталды".replace(",", " "))
    cols = st.columns(3)
    cols[0].metric("Байланысқан бөліктер", integer(len(analysis.components)))
    cols[1].metric("Байланысы жоқ клиенттер", integer(analysis.nodes.is_isolated.sum()))
    cols[2].metric("Ең үлкен бөлік", integer(analysis.components.n_nodes.max()))
    st.caption("Бөліктер байланыс бағытын уақытша ескермей анықталады. Louvain кластерлері мен рөлдерді «Рөлдер және басымдық» бөлімінде есептеңіз.")

    tabs = st.tabs(["Клиент көрсеткіштері", "Желі бөліктері", "Күндік аударымдар", "Нәтижелерді жүктеу"])
    with tabs[0]:
        _render_nodes(analysis)
    with tabs[1]:
        st.write("Бір бөліктегі клиенттер кемінде бір бағытталмаған жолмен байланысады. Байланысы жоқ әр клиент те жеке бөлік ретінде сақталған.")
        st.dataframe(analysis.components, hide_index=True, width="stretch", column_config={
            "component_id": "Бөлік №", "n_nodes": "Клиенттер", "n_edges": "Байланыстар",
            "n_seed": "Бастапқы клиенттер", "sum_kzt_internal": st.column_config.NumberColumn("Ішкі айналым, ₸", format="%.2f"),
            "is_isolated": "Оқшау клиент",
        })
    with tabs[2]:
        st.write("Жеке транзакциялар күн бойынша қосылған. Бірдей күн, сома және қатысушылары бар қайталанатын операциялар сақталған.")
        st.line_chart(analysis.daily.set_index("date")[["sum_kzt"]], x_label="Күн", y_label="Айналым, ₸", color="#136F83")
        st.dataframe(analysis.daily, hide_index=True, width="stretch", column_config={
            "date": "Күн", "sum_kzt": st.column_config.NumberColumn("Сома, ₸", format="%.2f"),
            "n_tx": "Операциялар", "n_senders": "Жіберушілер", "n_receivers": "Алушылар",
        })
    with tabs[3]:
        st.write("Бұл — 2-кезеңнің көрсеткіштері. ТЗ-дегі үш CSV файлы «Рөлдер және басымдық» бөлімінде жасалады.")
        for filename, frame, label in (
            ("node_metrics.csv", analysis.nodes, "Клиент көрсеткіштері · CSV"),
            ("components.csv", analysis.components, "Желі бөліктері · CSV"),
            ("daily_activity.csv", analysis.daily, "Күндік аударымдар · CSV"),
        ):
            st.download_button(label, frame.to_csv(index=False).encode("utf-8-sig"), file_name=filename, mime="text/csv")
        st.download_button("Граф есебі · JSON", json.dumps(analysis_summary(analysis), ensure_ascii=False, indent=2, allow_nan=False), file_name="graph_summary.json", mime="application/json")
        st.caption("CSV ашқанда gid/src/dst бағандарын мәтін ретінде импорттаңыз: кестелік редакторлар ұзын идентификаторларды дөңгелектеуі мүмкін.")

    with st.expander("Көрсеткіштер қалай есептеледі?"):
        st.markdown("""
        - **Кіріс/шығыс:** тек берілген графтағы сомалар және операциялар саны.
        - **Жіберушілер/алушылар саны:** өзге клиенттердің саны; өзіне аударым жеке қарсы тарап болып саналмайды. Оның сомасы мен операциялары сақталады.
        - **PageRank:** ақша сомасымен салмақталған бағытталған байланыстар көрсеткіші.
        - **Посредниктік орталықтық:** бағытталған ең қысқа жолдардағы аралық орын. Сома қашықтық ретінде қолданылмайды.
        - **Жететін seed саны:** клиентке бағытталған жолмен жететін өзге бастапқы клиенттер саны. Түйін өзі есептелмейді.
        - **Шығыс/кіріс:** тек байқалған ағындардың қатынасы. Seed, 4-буын және кірісі жоқ клиенттер үшін рөлге негіз ретінде қолдануға жарамсыз деп белгіленеді.
        - **1–2 күндік белгі:** кіріс операциясынан қатаң кейінгі күндегі ең жақын шығысқа дейінгі уақыт. Бақылаудың соңғы екі күніндегі кірістер үлес есебіне кірмейді. Бір күн ішіндегі реттілік пен дәл сол ақшаның қозғалысы анықталмайды.
        """)


def _render_nodes(analysis):
    labels = {
        "in_kzt": "Кіріс сомасы", "out_kzt": "Шығыс сомасы",
        "in_deg": "Жіберушілер саны", "out_deg": "Алушылар саны",
        "reachable_seed_count": "Жететін бастапқы клиенттер саны",
        "pagerank": "PageRank", "betweenness": "Посредниктік орталықтық",
    }
    sort_col, depth_col = st.columns([2, 1])
    sort_key = sort_col.selectbox("Сұрыптау көрсеткіші", list(labels), format_func=labels.get)
    depth_filter = depth_col.selectbox("Буын", ["Барлығы", "0", "1", "2", "3", "4"])
    shown = analysis.nodes
    if depth_filter != "Барлығы":
        shown = shown.loc[shown.depth.eq(int(depth_filter))]
    shown = shown.sort_values([sort_key, "gid"], ascending=[False, True])
    display_cols = ["gid", "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "reachable_seed_count", "pagerank", "betweenness"]
    st.caption(f"{len(shown)} клиент · алғашқы 100 жол. Бір көрсеткіш бойынша сұрыптау; толық тексеру кезегі «Рөлдер және басымдық» бөлімінде.")
    st.dataframe(safe_identifiers(shown[display_cols].head(100)), hide_index=True, width="stretch", column_config={
        "gid": st.column_config.TextColumn("gid"), "depth": "Буын", "is_seed": "Бастапқы",
        "in_deg": "Жіберушілер", "out_deg": "Алушылар",
        "in_kzt": st.column_config.NumberColumn("Кіріс, ₸", format="%.2f"),
        "out_kzt": st.column_config.NumberColumn("Шығыс, ₸", format="%.2f"),
        "reachable_seed_count": "Жететін seed",
        "pagerank": st.column_config.NumberColumn("PageRank", format="%.6f"),
        "betweenness": st.column_config.NumberColumn("Орталықтық", format="%.6f"),
    })
    gid_text = st.selectbox("Клиент көрсеткіштерін ашу · gid", [str(gid) for gid in analysis.nodes.gid], index=None, placeholder="gid енгізіңіз немесе тізімнен таңдаңыз", key="inspect_gid")
    if gid_text is None:
        return
    gid = int(gid_text)
    node = analysis.nodes.set_index("gid").loc[gid]
    st.markdown(f"**Клиент {gid_text}** · {int(node.depth)}-буын · {int(node.component_id)}-бөлік")
    cols = st.columns(4)
    cols[0].metric("Көрінетін кіріс", money(node.in_kzt))
    cols[1].metric("Көрінетін шығыс", money(node.out_kzt))
    cols[2].metric("Жіберушілер / алушылар", f"{node.in_deg} / {node.out_deg}")
    cols[3].metric("Жететін өзге seed", integer(node.reachable_seed_count))
    if node.is_isolated:
        st.info("Бұл клиенттің бақыланған байланыстары жоқ. Клиент графта және көрсеткіштер кестесінде сақталған.")
    if node.truncated_by_depth:
        st.warning("Клиент 4-буында. Кейінгі аударымдардың жоқтығы қаражат осы жерде қалды деген қорытындыға жеткіліксіз.")
    if node.is_seed:
        st.warning("Бастапқы клиенттің кірісі толық емес. Шығыс/кіріс қатынасы рөлді анықтауға қолданылмайды.")
    observed_ratio = "—" if pd.isna(node.observed_flow_ratio) else f"{node.observed_flow_ratio:.3f}"
    st.write(f"Көрінетін шығыс/кіріс қатынасы: **{observed_ratio}**. Қатынасқа сүйену: **{'шектеулерді ескеріп қолдануға болады' if node.ratio_usable else 'шектелген'}**.")
    temporal = "—" if pd.isna(node.next_out_1_2d_share) else f"{node.next_out_1_2d_share:.1%}"
    st.write(f"Белсенді күндер: **{integer(node.active_days)}**. Кейінгі 1–2 күнде шығыс байқалған кірістер үлесі: **{temporal}**; есепке кірген кіріс операциялары: **{integer(node.temporal_eligible_in_tx)}**.")
    mean_lag = "—" if pd.isna(node.mean_next_out_days) else f"{node.mean_next_out_days:.2f} күн"
    st.write(f"Кейінгі шығысқа дейінгі орташа уақыт: **{mean_lag}**.")
    st.caption("Орташа уақыт тек кейінгі шығысы байқалған, есепке жарамды кірістерден алынады; 2 күннен ұзақ аралық та кіреді. Кейінгі шығысы жоқ кірістер үлестің бөліміне кіреді, орташа уақытқа кірмейді.")
    st.caption("Уақыттың жақындығы — бақылау белгісі. Ол дәл осы кіріс ақшасының әрі қарай жіберілгенін дәлелдемейді.")
    paths = observed_seed_paths(analysis, gid, limit=5)
    if paths:
        st.markdown("**Бастапқы клиенттерден бағытталған жолдар**")
        for path in paths:
            st.code(" → ".join(str(item) for item in path), language=None)
        st.caption("Ең көбі 5 қысқа құрылымдық жол. Аударымдардың уақыт бойынша бірінен кейін бірі болғаны бұл жолдардан анықталмайды.")
    elif not node.is_isolated:
        st.caption("Өзге бастапқы клиенттен осы түйінге бағытталған жол табылмады.")
