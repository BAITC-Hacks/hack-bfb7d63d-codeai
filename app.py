"""MoneyMap · Local Parquet validation and Stage 2 graph analysis."""

from collections import Counter
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path

import streamlit as st

from moneymap.data import load_parquet_files, validate_dataset
from moneymap.demo import create_demo_frames, create_demo_zip
from moneymap.ui_graph import render_graph_tab, safe_identifiers


st.set_page_config(
    page_title="MoneyMap · Деректер және граф",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
    <style>
    .block-container { max-width: 1320px; padding-top: 2.4rem; padding-bottom: 3rem; }
    [data-testid="stSidebar"] { background: #10283f; }
    [data-testid="stSidebar"] p { color: #e7eff8; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color: #b2c5d8; }
    [data-testid="stSidebar"] button { background: #23445e; border-color: #46647d; }
    [data-testid="stSidebar"] button:hover { background: #2c526e; border-color: #89afc5; }
    h1 { font-size: clamp(1.8rem, 3vw, 2.45rem) !important; letter-spacing: -0.035em; }
    h2 { font-size: 1.45rem !important; }
    h3 { font-size: 1.12rem !important; }
    p, label, li { line-height: 1.6; }
    [data-testid="stMetric"] { padding: 1.05rem; border: 1px solid #dae3ec;
        background: white; border-radius: 12px; }
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    [data-testid="stFileUploader"] { background: #fff; border-radius: 12px; }
    .brand { font-size: 1.8rem; font-weight: 750; letter-spacing: -0.06em; margin: 0; }
    .brand-mark { color: #52d8c4 !important; margin-right: 0.4rem; }
    .eyebrow { font-size: .82rem; font-weight: 650; color: #4b647b; letter-spacing: .08em; }
    .step { padding: .7rem .85rem; border-radius: 8px; margin: .3rem 0; font-size: .9rem; }
    .step.active { background: #23475f; border-left: 3px solid #52d8c4; }
    .step.pending { color: #b2c5d8 !important; }
    .file-spec { padding: .8rem 0; border-bottom: 1px solid #e1e8ef; }
    .file-spec:last-child { border-bottom: none; }
    .file-spec strong { font-size: .98rem; }
    .file-spec p { color: #587086; font-size: .88rem; margin: .25rem 0 0; }
    @media (max-width: 700px) {
        .block-container { padding-top: 1.2rem; padding-left: 1rem; padding-right: 1rem; }
        [data-testid="stMetric"] { padding: .7rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def clear_report():
    for key in ("validation", "source", "checked_at", "analysis", "inspect_gid"):
        st.session_state.pop(key, None)


def save_result(result, source):
    clear_report()
    st.session_state.validation = result
    st.session_state.source = source
    st.session_state.checked_at = datetime.now().strftime("%H:%M:%S")


def number(value):
    return "—" if value is None else f"{value:,.0f}".replace(",", " ")


@st.cache_data(show_spinner=False)
def demo_zip():
    return create_demo_zip()


with st.sidebar:
    st.markdown('<p class="brand"><span class="brand-mark">◈</span>MoneyMap</p>', unsafe_allow_html=True)
    st.caption("Қаржылық байланыстарды талдау")
    st.divider()
    st.caption("ЖОБАНЫҢ КЕЗЕҢДЕРІ")
    st.markdown(
        """
        <div class="step">01 &nbsp; Деректерді қабылдау ✓</div>
        <div class="step active">02 &nbsp; Граф және көрсеткіштер</div>
        <div class="step pending">03 &nbsp; Рөлдер және басымдық</div>
        <div class="step pending">04 &nbsp; Карта және карточкалар</div>
        <div class="step pending">05 &nbsp; AI көмекші</div>
        <div class="step pending">06 &nbsp; Қорытынды тексеру</div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown("**Жергілікті режим**")
    st.caption("Файлдар осы компьютерде өңделеді. Бұл кезеңде сыртқы API шақырылмайды.")
    st.download_button(
        "Демо файлдарын жүктеу",
        data=demo_zip(),
        file_name="moneymap-synthetic-demo.zip",
        mime="application/zip",
        width="stretch",
    )
    st.caption("Жасанды деректер · интерфейсті сынауға арналған")

st.markdown('<div class="eyebrow">ЖҰМЫС КЕҢІСТІГІ / 01–02</div>', unsafe_allow_html=True)
st.title("Деректер және граф")
st.write("Кейс файлдарын тексеріп, клиенттердің байланыстарын, ақша ағынын және күндік көрсеткіштерін есептеңіз.")

left, right = st.columns([1.65, 1], gap="large")
with left:
    with st.container(border=True):
        st.subheader("Кейс файлдары")
        uploaded = st.file_uploader(
            "nodes.parquet, edges.parquet және transactions.parquet",
            type=["parquet"],
            accept_multiple_files=True,
            key="uploads",
            on_change=clear_report,
            help="Әр файл 20 МБ-тан аспауы керек. Файл атауларын өзгертпеңіз.",
        )
        st.caption("3 файл · Parquet · әрқайсысы 20 МБ-қа дейін")
        actions = st.columns([1, 1.3])
        check_clicked = actions[0].button("Файлдарды тексеру", type="primary", disabled=not uploaded, width="stretch")
        demo_clicked = actions[1].button("Демо деректермен тексеру", width="stretch")
        case_dir = Path(__file__).resolve().parent / "data" / "case"
        case_names = ("nodes.parquet", "edges.parquet", "transactions.parquet")
        if all((case_dir / name).is_file() for name in case_names):
            if st.button("Берілген кейсті ашу", width="stretch"):
                with st.spinner("Жергілікті кейс файлдары тексеріліп жатыр…"):
                    try:
                        save_result(load_parquet_files({name: (case_dir / name).read_bytes() for name in case_names}), "local_case")
                    except OSError:
                        clear_report()
                        st.error("Жергілікті файлдарды оқу мүмкін болмады. Үш Parquet файлын жоғарыдан жүктеңіз.")
            st.caption("Осы компьютердегі data/case папкасынан оқылады.")
        if check_clicked:
            clear_report()
            counts = Counter(file.name for file in uploaded)
            if any(count > 1 for count in counts.values()):
                st.error("Бір атаумен бірнеше файл таңдалған. Әр файлдың бір нұсқасын ғана қалдырыңыз.")
            elif any(file.size > 20 * 1024 * 1024 for file in uploaded):
                st.error("Файл көлемі 20 МБ шегінен асты.")
            else:
                with st.spinner("Файлдар мен аударымдар тексеріліп жатыр…"):
                    save_result(load_parquet_files({file.name: file.getvalue() for file in uploaded}), "upload")
        if demo_clicked:
            with st.spinner("Жасанды деректер тексеріліп жатыр…"):
                save_result(validate_dataset(create_demo_frames()), "demo")
with right:
    with st.container(border=True):
        st.subheader("Қажетті деректер")
        st.markdown(
            """
            <div class="file-spec"><strong>nodes.parquet</strong><p>Клиенттер · gid, depth, is_seed</p></div>
            <div class="file-spec"><strong>edges.parquet</strong><p>Байланыстар · src, dst, sum_kzt, n_tx, depth</p></div>
            <div class="file-spec"><strong>transactions.parquet</strong><p>Операциялар · src, dst, date, sum_kzt</p></div>
            """,
            unsafe_allow_html=True,
        )

result = st.session_state.get("validation")
if result is None:
    if uploaded:
        st.info(f"{len(uploaded)} файл таңдалды. Нәтижені алу үшін «Файлдарды тексеру» батырмасын басыңыз.")
    else:
        st.info("Нақты кейс файлдары әлі жүктелген жоқ. Жұмысты көру үшін «Демо деректермен тексеру» батырмасын басыңыз.")
    with st.expander("Тексеру нені қамтиды?"):
        st.write("Міндетті өрістер, дерек түрлері, қайталанатын клиенттер, белгісіз жіберушілер мен алушылар, оң сомалар және операциялардың байланыстар кестесімен сәйкестігі тексеріледі.")
        st.write("Төртінші буын мен бастапқы клиенттердің толық емес кірістері жеке ескертіледі. Рөлдер мен тексеру басымдығы келесі кезеңдерде есептеледі.")
    st.stop()

st.divider()
if st.session_state.source == "demo":
    st.warning("ДЕМО РЕЖИМІ · Бұл — жасанды сынақ деректері. Төмендегі сандар нақты кейстің нәтижесі емес.")
elif st.session_state.source == "local_case":
    st.caption("Дереккөзі: ұйымдастырушы берген үш файлдың жергілікті көшірмесі.")

result_head, result_time = st.columns([3, 1])
result_head.subheader("Тексеру нәтижесі")
result_time.caption(f"Соңғы тексеру: {st.session_state.checked_at}")
errors = [issue for issue in result.issues if issue.severity == "error"]
warnings = [issue for issue in result.issues if issue.severity == "warning"]
if result.valid:
    st.success("Құрылым мен сәйкестік тексерілді. Деректер келесі талдау кезеңіне дайын.")
else:
    st.error(f"Тексеру аяқталды: {len(errors)} қате табылды. Талдауды бастау үшін төмендегі қателерді түзетіңіз.")

metrics = result.metrics
for col, label, key in zip(st.columns(4), ["Клиенттер", "Байланыстар", "Операциялар", "Бастапқы клиенттер"], ["nodes", "edges", "transactions", "seeds"]):
    col.metric(label, number(metrics.get(key)))

tabs = st.tabs(["Деректер сапасы", "Граф көрсеткіштері", "Кестелерді қарау", "Тексеру есебі"])
with tabs[0]:
    if errors:
        for issue in errors:
            st.error(f"{issue.file + ': ' if issue.file else ''}{issue.message}")
    if warnings:
        st.markdown("**Талдау кезінде ескерілетін шектеулер**")
        for issue in warnings:
            st.warning(issue.message)
    for issue in result.issues:
        if issue.severity == "info":
            st.info(issue.message)
    if not result.issues:
        st.write("Қате немесе ескерту табылған жоқ.")
    a, b, c = st.columns(3)
    a.metric("Бақыланған айналым, ₸", number(metrics.get("turnover_kzt")))
    b.metric("4-буындағы клиенттер", number(metrics.get("boundary_nodes")))
    c.metric("Байланысы жоқ клиенттер", number(metrics.get("isolated_nodes")))
    if metrics.get("min_date"):
        st.caption(f"Бақылау кезеңі: {metrics['min_date']} — {metrics['max_date']}")
    st.caption("Айналым — көрінетін аударымдардың қосындысы. Бір ақша бірнеше байланыс арқылы өтуі мүмкін.")
with tabs[1]:
    render_graph_tab(result)
with tabs[2]:
    names = [name for name in ("nodes", "edges", "transactions") if name in result.frames]
    if names:
        table_name = st.selectbox("Кесте", names, format_func=lambda name: f"{name}.parquet")
        frame = result.frames[table_name]
        st.caption(f"Барлығы {len(frame):,} жол. Алғашқы 100 жол көрсетілген.".replace(",", " "))
        st.dataframe(safe_identifiers(frame.head(100)), hide_index=True, width="stretch")
    else:
        st.info("Көрсетуге болатын кесте жоқ.")
with tabs[3]:
    report = {
        "stage": 1,
        "source": {"demo": "synthetic_demo", "local_case": "local_case_files", "upload": "uploaded_files"}[st.session_state.source],
        "valid": result.valid,
        "metrics": result.metrics,
        "issues": [asdict(issue) for issue in result.issues],
    }
    st.write("Есепте тек тексеру нәтижелері бар. Клиенттердің рөлдері мен басымдығы бұл кезеңде есептелмейді.")
    st.download_button(
        "Тексеру есебін жүктеу · JSON",
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        file_name="validation_report.json",
        mime="application/json",
    )
    st.json(report, expanded=False)
