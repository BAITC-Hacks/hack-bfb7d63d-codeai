"""MoneyMap: an AML analyst workspace with local, explainable computation."""

from collections import Counter
from dataclasses import asdict
from datetime import datetime
from html import escape
import json
from pathlib import Path

import altair as alt
import streamlit as st

from moneymap.data import load_parquet_files, validate_dataset
from moneymap.demo import create_demo_frames, create_demo_zip
from moneymap.ui_design import apply_design, page_header, welcome_panel, guide, footer, candidate_row, role_distribution
from moneymap.ui_graph import render_graph_tab, safe_identifiers, integer
from moneymap.ui_roles import ROLE_LABELS, render_queue_page, render_clusters_page, render_exports, ensure_role_analysis
from moneymap.ui_map import render_map_tab
from moneymap.ui_ai import render_ai_tab
from moneymap.ui_state import clear_map_state, clear_ai_state, queue_map_navigation


st.set_page_config(page_title="MoneyMap · AML жұмыс кеңістігі", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
apply_design(collapsed=st.session_state.get("sidebar_compact", False))
ROOT = Path(__file__).resolve().parent
PAGES = ["Шолу", "Тексеру кезегі", "Желі картасы", "Кластерлер", "Анықтама", "Деректер"]
PAGE_LABELS = {"Шолу": "Шолу", "Тексеру кезегі": "Тексеру кезегі", "Желі картасы": "Желі картасы", "Кластерлер": "Кластерлер", "Анықтама": "Анықтама", "Деректер": "Деректер және экспорт"}
TITLES = {
    "Шолу": ("Қаржылық желіні талдау", "Кімнен бастау керек? Ақша ағынын, байланыстарды және тексеру негіздерін бір жерден қараңыз."),
    "Тексеру кезегі": ("Тексеру кезегі", "Басымдығы жоғары клиенттер. Әр ұсыныстың артында — бақыланған көрсеткіштер мен түсінікті ереже."),
    "Желі картасы": ("Ақша ағынының картасы", "Клиенттің айналасын ашып, ақша бағытын және байланыстың нақты негізін зерттеңіз."),
    "Кластерлер": ("Желінің қаржылық құрылымы", "Байланысқан топтар, олардың арасындағы ағындар және ықтимал қызметі туралы гипотезалар."),
    "Анықтама": ("Талдаушының анықтамасы", "Клиент, басымдық немесе кластер туралы тексерілетін фактілерді жинақтаңыз."),
    "Деректер": ("Деректер және нәтижелер", "Дерек сапасын, бастапқы кестелерді және есептеу көрсеткіштерін тексеріп, нәтижені жүктеңіз."),
}


def clear_report():
    clear_map_state()
    clear_ai_state()
    for key in ("validation", "source", "checked_at", "analysis", "inspect_gid", "role_analysis", "role_gid", "role_cluster", "role_filter"):
        st.session_state.pop(key, None)


def save_result(result, source):
    clear_report()
    st.session_state.validation = result
    st.session_state.source = source
    st.session_state.checked_at = datetime.now().strftime("%H:%M:%S")
    st.session_state.pending_workspace_page = "Шолу"


def go(page):
    st.session_state.pending_workspace_page = page
    st.rerun()


def toggle_sidebar():
    st.session_state.sidebar_compact = not st.session_state.get("sidebar_compact", False)


@st.cache_data(show_spinner=False)
def demo_zip():
    return create_demo_zip()


def render_intake():
    with st.expander("Кейс деректері · ашу немесе ауыстыру", expanded=st.session_state.get("validation") is None):
        left, right = st.columns([1.55, 1], gap="large")
        with left:
            st.markdown("**Кейспен жұмысты бастау**")
            st.caption("Берілген жиынды ашыңыз немесе өзіңіздің үш Parquet файлыңызды жүктеңіз.")
            case_dir = ROOT / "data" / "case"
            names = ("nodes.parquet", "edges.parquet", "transactions.parquet")
            actions = st.columns(2)
            if all((case_dir / name).is_file() for name in names):
                if actions[0].button("Берілген кейсті ашу", type="primary", width="stretch", key="open_case"):
                    with st.spinner("Кейс деректері тексеріліп жатыр…"):
                        try:
                            save_result(load_parquet_files({name: (case_dir / name).read_bytes() for name in names}), "local_case")
                        except OSError:
                            clear_report()
                            st.error("Кейс файлдары оқылмады. Үш Parquet файлын төменнен жүктеңіз.")
                        else:
                            st.rerun()
            if actions[1].button("Демо деректермен тексеру", width="stretch", key="load_demo"):
                save_result(validate_dataset(create_demo_frames()), "demo")
                st.rerun()
            uploaded = st.file_uploader("nodes.parquet, edges.parquet және transactions.parquet", type=["parquet"], accept_multiple_files=True, key="uploads", on_change=clear_report, help="Әр файл 20 МБ-тан аспауы керек. Үш файлдың атауын сақтаңыз.")
            if st.button("Файлдарды тексеру", disabled=not uploaded, width="stretch", key="validate_upload"):
                clear_report()
                counts = Counter(file.name for file in uploaded)
                if any(count > 1 for count in counts.values()):
                    st.error("Бір атаумен бірнеше файл таңдалған. Әр файлдың бір нұсқасын қалдырыңыз.")
                elif any(file.size > 20 * 1024 * 1024 for file in uploaded):
                    st.error("Файл көлемі 20 МБ шегінен асты.")
                else:
                    with st.spinner("Файлдар мен аударымдар тексеріліп жатыр…"):
                        save_result(load_parquet_files({file.name: file.getvalue() for file in uploaded}), "upload")
                    st.rerun()
        with right:
            guide()
            st.caption("Деректер осы компьютерде өңделеді. Бастапқы файлдар өзгертілмейді.")


def render_quality(result):
    errors = [issue for issue in result.issues if issue.severity == "error"]
    if result.valid:
        st.success("Құрылым мен сәйкестік тексерілді. Деректер келесі талдау кезеңіне дайын.")
    else:
        st.error(f"{len(errors)} қате табылды. Талдауға дейін деректерді түзетіңіз.")
    for issue in result.issues:
        prefix = f"{issue.file}: " if issue.file else ""
        getattr(st, {"error": "error", "warning": "warning", "info": "info"}.get(issue.severity, "info"))(prefix + issue.message)
    st.caption("Айналым — көрінетін аударымдардың қосындысы. Бір ақша бірнеше байланыс арқылы өтуі мүмкін.")


def render_overview(result):
    metrics = result.metrics
    for col, label, key in zip(st.columns(4), ["Клиенттер", "Бағытталған байланыстар", "Аударымдар", "Бастапқы клиенттер"], ["nodes", "edges", "transactions", "seeds"]):
        col.metric(label, integer(metrics.get(key)))
    if not result.valid:
        render_quality(result)
        return
    roles = st.session_state.get("role_analysis")
    if roles is None:
        st.write("")
        a, b = st.columns([1.55, 1], gap="large")
        with a:
            welcome_panel()
        with b:
            with st.container(border=True):
                st.subheader("Деректер талдауға дайын")
                st.write("Барлық клиенттің рөлін, тексеру басымдығын және кластерлерді бірге есептеңіз.")
                st.caption("Нәтиже нақты ережелермен түсіндіріледі. AI кілті қажет емес.")
                if st.button("Талдауды бастау", type="primary", width="stretch", key="overview_analyze"):
                    with st.spinner("Қаржылық желі талданып жатыр…"):
                        prepared = ensure_role_analysis(result)
                    if prepared is not None:
                        st.rerun()
                st.markdown(f'<div class="mm-note"><b>{integer(metrics.get("boundary_nodes"))} клиент</b> бақылаудың 4-буын шекарасында. Олардың кейінгі шығысы белгісіз.</div>', unsafe_allow_html=True)
        return
    graph = st.session_state.analysis
    st.write("")
    left, right = st.columns([1.7, 1], gap="large")
    with left:
        with st.container(border=True, key="overview_flow"):
            st.markdown('<div class="mm-panel-label">БАҚЫЛАНҒАН АҚША АҒЫНЫ</div>', unsafe_allow_html=True)
            turnover = f"{metrics.get('turnover_kzt', 0):,.2f}".replace(",", " ")
            st.markdown(f'<div class="mm-turnover">{turnover}<span>₸</span></div>', unsafe_allow_html=True)
            st.caption("Күндік аударымдар · бір қаражат бірнеше рет есепке алынуы мүмкін")
            if not graph.daily.empty:
                chart = alt.Chart(graph.daily).mark_area(line={"color": "#1b8e87", "strokeWidth": 2.3}, color=alt.Gradient(gradient="linear", stops=[alt.GradientStop(color="#a4dace", offset=0), alt.GradientStop(color="#f6fbf9", offset=1)], x1=1, x2=1, y1=0, y2=1)).encode(
                    x=alt.X("date:T", title=None, axis=alt.Axis(format="%d %b", labelColor="#7b8d9b", grid=False, tickCount=6)),
                    y=alt.Y("sum_kzt:Q", title=None, axis=alt.Axis(format="~s", labelColor="#7b8d9b", gridColor="#eef2f4", tickCount=4)),
                    tooltip=[alt.Tooltip("date:T", title="Күн", format="%d.%m.%Y"), alt.Tooltip("sum_kzt:Q", title="Сома, ₸", format=",.2f"), alt.Tooltip("n_tx:Q", title="Операциялар")],
                ).properties(height=207).configure_view(strokeWidth=0)
                st.altair_chart(chart, width="stretch")
    with right:
        with st.container(border=True, key="overview_roles"):
            st.subheader("Рөлдер құрылымы")
            st.caption("Бақыланған деректерге сүйенген гипотезалар")
            role_distribution(roles.nodes_roles.role.value_counts().to_dict(), ROLE_LABELS)
    left, right = st.columns([1.7, 1], gap="large")
    with left:
        with st.container(border=True, key="overview_queue_panel"):
            a, b = st.columns([2, 1])
            a.subheader("Алдымен тексеруге ұсынылады")
            if b.button("Толық кезек →", key="overview_queue", width="stretch"):
                go("Тексеру кезегі")
            st.caption("Ұпай — тексеру басымдығы. Кінәлілік ықтималдығы емес.")
            for row in roles.top_nodes.head(4).itertuples(index=False):
                a, b = st.columns([4, 1])
                with a:
                    candidate_row(row.rank, str(row.gid), ROLE_LABELS.get(row.role, row.role), row.priority_score)
                with b:
                    if st.button("Карта ↗", key=f"overview_map_{row.gid}", width="stretch"):
                        queue_map_navigation(gid=str(row.gid))
    with right:
        with st.container(border=True, key="overview_limits"):
            st.subheader("Талдауда ескеріңіз")
            boundary = integer(metrics.get("boundary_nodes"))
            isolated = integer(metrics.get("isolated_nodes"))
            st.markdown(f'<div class="mm-note"><b>{boundary} шекаралық клиент.</b> Кейінгі аударымдары зерттелмеген.</div><div class="mm-note"><b>{isolated} оқшау клиент.</b> Бақыланған байланысы жоқ; барлығы сақталды.</div>', unsafe_allow_html=True)
            contradictions = int(graph.nodes["temporal_contradiction"].sum()) if "temporal_contradiction" in graph.nodes else 0
            if contradictions:
                st.markdown(f'<div class="mm-note"><b>{contradictions} уақыттық қайшылық.</b> Бақыланған шығыс алғашқы кірістен бұрын болған. Бұл белгі рөлде ескеріледі.</div>', unsafe_allow_html=True)
            if st.button("Дерек сапасын қарау →", key="overview_quality", width="stretch"):
                st.session_state.data_tab_hint = "Деректер сапасы"
                go("Деректер")
    with st.container(border=True, key="overview_actions"):
        a, b, c = st.columns([2, 1, 1])
        a.markdown(f"**{len(roles.clusters)} кластер · {len(roles.top_nodes)} басым клиент**")
        a.caption("Нәтижені тексеріп, аналитикалық анықтама мен үш CSV алыңыз.")
        if b.button("Кластерлер →", key="overview_clusters", width="stretch"):
            go("Кластерлер")
        if c.button("Нәтижені жүктеу →", key="overview_export", width="stretch"):
            st.session_state.data_tab_hint = "Экспорт"
            go("Деректер")


def render_data_page(result):
    labels = ["Экспорт", "Деректер сапасы", "Бастапқы кестелер", "Граф көрсеткіштері"]
    tabs = st.tabs(labels, default=st.session_state.get("data_tab_hint", "Экспорт"))
    with tabs[0]:
        if st.session_state.get("role_analysis") is not None:
            render_exports(st.session_state.role_analysis)
        else:
            st.info("Үш қорытынды CSV алу үшін алдымен талдауды орындаңыз.")
            if st.button("Нәтижелерді есептеу", key="data_analyze", type="primary"):
                if ensure_role_analysis(result) is not None:
                    st.rerun()
        report = {"source": st.session_state.source, "valid": result.valid, "metrics": result.metrics, "issues": [asdict(issue) for issue in result.issues]}
        with st.expander("Дерек сапасының есебі"):
            st.download_button("Тексеру есебін жүктеу · JSON", json.dumps(report, ensure_ascii=False, indent=2, default=str), file_name="validation_report.json", mime="application/json")
            st.json(report, expanded=False)
    with tabs[1]:
        render_quality(result)
    with tabs[2]:
        names = [name for name in ("nodes", "edges", "transactions") if name in result.frames]
        if names:
            name = st.selectbox("Кесте", names, format_func=lambda value: f"{value}.parquet")
            frame = result.frames[name]
            st.caption(f"Барлығы {integer(len(frame))} жол. Алғашқы 100 жол көрсетілген; gid дәл мәтін ретінде сақталады.")
            st.dataframe(safe_identifiers(frame.head(100)), hide_index=True, width="stretch")
    with tabs[3]:
        render_graph_tab(result)


pending_page = st.session_state.pop("pending_workspace_page", None)
if pending_page in PAGES:
    st.session_state.workspace_page = pending_page
with st.sidebar:
    st.markdown('<div class="mm-brand" aria-label="MoneyMap"><span class="mm-brand-icon" aria-hidden="true">⌘</span><span class="mm-brand-name">MoneyMap</span></div><div class="mm-brand-sub">FINANCIAL INTELLIGENCE</div>', unsafe_allow_html=True)
    compact = st.session_state.get("sidebar_compact", False)
    st.button("Мәзірді ашу" if compact else "Мәзірді жинау", key="sidebar_toggle", on_click=toggle_sidebar, help="Бөлім атауларын көрсету" if compact else "Тек бөлім белгішелерін қалдыру", width="stretch")
    st.markdown('<div class="mm-nav-label">ТАЛДАУ КЕҢІСТІГІ</div>', unsafe_allow_html=True)
    page = st.radio("Жұмыс бөлімі", PAGES, format_func=PAGE_LABELS.get, key="workspace_page", label_visibility="collapsed")
    with st.container(key="sidebar_details"):
        st.divider()
        result = st.session_state.get("validation")
        if result is not None:
            st.caption("АҒЫМДАҒЫ КЕЙС")
            source_name = {"demo": "Жасанды демо", "local_case": "Ұйымдастырушының деректері", "upload": "Жүктелген деректер"}.get(st.session_state.source, "Кейс")
            st.markdown(f"**{source_name}**")
            st.caption(f"{integer(result.metrics.get('nodes'))} клиент · {integer(result.metrics.get('transactions'))} аударым")
            st.caption(f"{result.metrics.get('min_date', '—')} — {result.metrics.get('max_date', '—')}")
        st.markdown('<div class="mm-side-note"><b>● Жергілікті жұмыс режимі</b><span>Граф пен есептер осы компьютерде өңделеді. Рөлдер — тексеруге арналған гипотезалар.</span></div>', unsafe_allow_html=True)
        with st.expander("Демо және нұсқаулық"):
            st.caption("Жасанды деректермен жұмысты тексеруге болады. Бұл нақты кейс нәтижесі емес.")
            st.download_button("Демо файлдарын жүктеу", demo_zip(), file_name="moneymap-synthetic-demo.zip", mime="application/zip", width="stretch")
            st.caption("Кезек → клиент → карта → дәлел → экспорт. AI қолдану міндетті емес.")

page_header(*TITLES[page])
render_intake()
result = st.session_state.get("validation")
if result is None:
    left, right = st.columns([1.6, 1], gap="large")
    with left:
        welcome_panel()
    with right:
        with st.container(border=True):
            st.subheader("Бір желі. Тексерілетін негіздер.")
            st.write("Кіріс пен шығысты, ықтимал рөлдерді және бастапқы клиенттермен байланыстарды бірге зерттеңіз.")
            st.caption("Нақты кейс файлдары әлі жүктелген жоқ. Жоғарыдан кейсті ашыңыз немесе демоны таңдаңыз.")
    footer()
    st.stop()

source_name = {"demo": "Жасанды демо", "local_case": "Ұйымдастырушының кейсі", "upload": "Жүктелген кейс"}[st.session_state.source]
st.markdown(f'<div class="mm-casebar"><span><strong>{escape(source_name)}</strong> · {escape(str(result.metrics.get("min_date", "—")))} — {escape(str(result.metrics.get("max_date", "—")))}</span><span>{"Құрылымы тексерілді" if result.valid else "Деректе қате бар"} · {escape(st.session_state.checked_at)}</span></div>', unsafe_allow_html=True)
if st.session_state.source == "demo":
    st.warning("ДЕМО РЕЖИМІ · Жасанды сынақ деректері. Бұл нақты кейстің нәтижесі емес.")
if not result.valid and page != "Деректер":
    render_quality(result)
else:
    if page == "Шолу":
        render_overview(result)
    elif page == "Тексеру кезегі":
        render_queue_page(result)
    elif page == "Желі картасы":
        render_map_tab(result)
    elif page == "Кластерлер":
        render_clusters_page(result)
    elif page == "Анықтама":
        render_ai_tab(result)
    else:
        render_data_page(result)
footer()



