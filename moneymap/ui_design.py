"""Offline visual language for the analyst workspace; no remote assets."""

from html import escape
from urllib.parse import quote

import streamlit as st
from moneymap.graph_view import ROLE_COLORS


def apply_design(*, collapsed=False):
    st.html("""<style>
    :root { --ink:#152d43; --muted:#6a7d8f; --teal:#147d76; --line:#e1e8ed; }
    html, body, [class*="css"] { font-family: 'Segoe UI', Arial, sans-serif; }
    .stApp { background:#f3f6f8; }
    .block-container { max-width:1510px; padding:4.3rem 2.4rem 3rem; }
    [data-testid="stHeader"] { background:rgba(243,246,248,.93); }
    [data-testid="stAppDeployButton"], [data-testid="stMainMenu"] { display:none; }
    h1 { font-size:2rem !important; line-height:1.18 !important; letter-spacing:-.055em; font-weight:700 !important; margin-bottom:.25rem !important; }
    h2 { font-size:1.35rem !important; letter-spacing:-.025em; }
    h3 { font-size:1.06rem !important; letter-spacing:-.02em; }
    p, li { line-height:1.6; }
    [data-testid="stCaptionContainer"] { color:var(--muted); }
    [data-testid="stSidebar"] { background:#102b3c; border-right:1px solid #173c4f; }
    [data-testid="stSidebar"] > div:first-child { padding-top:2rem; }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] label { color:#dce7ed; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color:#88a4b5; }
    [data-testid="stSidebar"] hr { border-color:#294456; }
    [data-testid="stSidebar"] [data-testid="stRadio"] > label { display:none; }
    [data-testid="stSidebar"] [role="radiogroup"] { gap:7px; width:100%; }
    [data-testid="stSidebar"] [role="radiogroup"] > div { width:100%; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] { display:block; width:100%; border-radius:8px; padding:11px 13px; transition:background .15s; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"]:hover { background:#1b3d4e; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] { background:#1a494f; box-shadow:inset 3px 0 #66d4b9; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child { display:none; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] p { font-size:.9rem; }
    [data-testid="stSidebar"] [data-baseweb="radio"] { margin:0; border-radius:9px; padding:11px 13px; transition:background .15s; }
    [data-testid="stSidebar"] [data-baseweb="radio"]:hover { background:#1b3d4e; }
    [data-testid="stSidebar"] [data-baseweb="radio"]:has(input:checked) { background:#1a494f; box-shadow:inset 3px 0 #66d4b9; }
    [data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child { display:none; }
    [data-testid="stSidebar"] [data-baseweb="radio"] p { font-size:.92rem; }
    [data-testid="stSidebar"] button { background:#1b3c4e; color:#dce7ed; border:1px solid #355263; border-radius:8px; }
    [data-testid="stSidebar"] button:hover { background:#285062; border-color:#68bdb2; }
    [data-testid="stSidebar"] [data-testid="stIconMaterial"] { color:#c4dbe5; }
    [data-testid="stButton"] button, [data-testid="stDownloadButton"] button { min-height:41px; border-radius:8px; font-weight:600; border-color:#d7e1e7; }
    [data-testid="stButton"] button[kind="primary"] { background:#147d76; border-color:#147d76; box-shadow:0 3px 8px #147d7614; }
    [data-testid="stButton"] button[kind="primary"]:hover { background:#0f655f; border-color:#0f655f; }
    button:focus-visible, input:focus-visible { outline:3px solid #53b9b1 !important; outline-offset:2px; }
    [data-testid="stMetric"] { padding:18px 20px; border:1px solid var(--line); border-radius:10px; background:white; box-shadow:0 3px 12px #173b5503; }
    [data-testid="stMetricLabel"] p { color:#60758a; font-size:.78rem; font-weight:600; }
    [data-testid="stMetricValue"] { font-size:1.75rem; font-weight:650; letter-spacing:-.05em; color:var(--ink); }
    [data-testid="stVerticalBlockBorderWrapper"] > div { border-color:var(--line) !important; border-radius:12px !important; }
    [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlockBorderWrapper"] > div { border-radius:9px !important; }
    .st-key-overview_flow, .st-key-overview_roles, .st-key-overview_queue_panel, .st-key-overview_limits, .st-key-overview_actions { background:white; border-color:var(--line)!important; border-radius:12px; }
    [data-testid="stExpander"] { border:1px solid var(--line); border-radius:9px; background:#fff; }
    [data-testid="stExpander"] details summary { font-size:.85rem; }
    [data-testid="stSidebar"] [data-testid="stExpander"] { background:#163647; border-color:#31505f; }
    [data-testid="stSidebar"] [data-testid="stExpander"] details summary { color:#dce7ed; }
    [data-testid="stDataFrame"] { border-radius:8px; overflow:hidden; border:1px solid #e4ebef; }
    [data-testid="stTabs"] [data-baseweb="tab-list"] { gap:20px; border-bottom:1px solid var(--line); }
    [data-testid="stTabs"] [data-baseweb="tab"] { height:42px; font-size:.86rem; }
    [data-testid="stAlert"] { border-radius:8px; }
    [data-testid="stTextInput"] input { font-family:'Segoe UI',Arial,sans-serif; }
    [data-testid="stFileUploader"] { border-radius:8px; }
    .mm-brand {display:flex;align-items:center;gap:11px;color:#fff;font-size:1.45rem;font-weight:750;letter-spacing:-.045em;margin-bottom:6px;}
    .mm-brand-icon {width:36px;height:36px;display:grid;place-items:center;background:#66d4b9;color:#102b3c;border-radius:9px;font-size:25px;line-height:1;}
    .mm-brand-sub {font-size:.67rem;letter-spacing:.17em;color:#89a9b9;margin:0 0 23px 47px;}
    .mm-nav-label {color:#7193a6;font-size:.63rem;letter-spacing:.17em;font-weight:700;margin:23px 0 13px;}
    .mm-side-note {padding:15px;border:1px solid #31505f;border-radius:10px;background:#163647;margin-top:18px;}
    .mm-side-note b {font-size:.82rem;color:#dfecef;display:block;margin-bottom:6px;}
    .mm-side-note span {font-size:.75rem;color:#91aebb;line-height:1.6;display:block;}
    .mm-live {display:inline-flex;align-items:center;gap:7px;font-size:.72rem;color:#41716b;background:#e7f3ed;border:1px solid #d4e9df;border-radius:20px;padding:6px 11px;white-space:nowrap;}
    .mm-live:before {content:'';height:6px;width:6px;background:#2ca27d;border-radius:50%;}
    .mm-eyebrow {color:#688092;letter-spacing:.15em;font-size:.65rem;font-weight:700;margin-bottom:12px;}
    .mm-header-meta {display:flex;justify-content:flex-end;align-items:center;gap:12px;padding-top:19px;}
    .mm-subtitle {color:#728294;font-size:.87rem;max-width:760px;margin-bottom:22px;}
    .mm-casebar {display:flex;justify-content:space-between;align-items:center;gap:12px;color:#6b8090;font-size:.74rem;padding:11px 0 18px;flex-wrap:wrap;}
    .mm-casebar strong {color:#365364;font-weight:600;}
    .mm-welcome {background:#102f40;position:relative;border-radius:14px;color:#eff8f7;padding:35px 35px 30px;overflow:hidden;min-height:242px;}
    .mm-welcome:after {content:'';position:absolute;right:-60px;top:-80px;width:280px;height:280px;border:1px solid #31566b;border-radius:50%;box-shadow:0 0 0 45px #173c4d,0 0 0 46px #31566b,0 0 0 95px #173c4d66;opacity:.5;pointer-events:none;}
    .mm-welcome small {display:block;color:#85d2bd;font-size:.66rem;letter-spacing:.16em;font-weight:700;margin-bottom:17px;position:relative;z-index:1;}
    .mm-welcome h2 {font-size:1.8rem !important;color:#fff !important;line-height:1.22 !important;max-width:450px;position:relative;z-index:1;}
    .mm-welcome p {color:#aac2cb;font-size:.87rem;max-width:425px;margin-top:13px;position:relative;z-index:1;}
    .mm-pills {display:flex;gap:8px;flex-wrap:wrap;margin-top:20px;position:relative;z-index:1;}
    .mm-pills span {font-size:.67rem;background:#254959;color:#d1e6e8;border:1px solid #3b6070;padding:5px 9px;border-radius:5px;}
    .mm-panel-label {font-size:.65rem;color:#78909f;letter-spacing:.12em;font-weight:700;margin:0 0 12px;}
    .mm-turnover {font-size:1.85rem;letter-spacing:-.045em;font-weight:650;color:#1b384d;margin:5px 0;}
    .mm-turnover span {font-size:1rem;color:#81929f;margin-left:7px;font-weight:400;}
    .mm-row {display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid #edf1f4;}
    .mm-row:last-child {border:0;}
    .mm-rank {font-size:.7rem;color:#7c90a1;width:24px;font-family:Consolas,monospace;}
    .mm-id {font-family:Consolas,monospace;font-size:.81rem;letter-spacing:-.02em;font-weight:600;color:#294355;}
    .mm-role {font-size:.73rem;color:#78909b;margin-top:3px;}
    .mm-score {margin-left:auto;font-family:Consolas,monospace;color:#147d76;font-weight:700;font-size:.9rem;}
    .mm-note {border-left:3px solid #d4aa50;padding:11px 14px;background:#faf5e9;border-radius:0 7px 7px 0;color:#8b7544;font-size:.78rem;margin:9px 0;}
    .mm-note b {color:#786237;}
    .mm-footer {display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-top:32px;padding-top:15px;border-top:1px solid var(--line);font-size:.68rem;color:#8396a4;}
    .mm-role-line {display:flex;align-items:center;gap:10px;margin:12px 0;font-size:.77rem;color:#577184;}
    .mm-dot {width:8px;height:8px;border-radius:50%;flex:none;}
    .mm-role-line b {margin-left:auto;color:#1d3c50;font-family:Consolas,monospace;}
    .mm-guide {padding:11px 0;border-bottom:1px solid #edf1f4;display:flex;gap:13px;align-items:flex-start;}
    .mm-guide:last-child {border:0;}
    .mm-guide>span {font-size:.75rem;background:#e9f3ef;color:#287971;min-width:26px;height:26px;border-radius:7px;display:grid;place-items:center;font-weight:700;}
    .mm-guide b {font-size:.87rem;color:#304e60;}
    .mm-guide p {font-size:.76rem;color:#78909e;margin:3px 0 0;}
    @media(max-width:1000px){.block-container{padding:4rem 1.35rem 2rem;}.mm-header-meta{padding-top:0;justify-content:flex-start;}}
    @media(max-width:650px){h1{font-size:1.65rem!important}.block-container{padding:4rem 1rem 2rem;}.mm-welcome{padding:25px;min-height:220px;}.mm-welcome h2{font-size:1.55rem!important}.mm-header-meta{display:none}.mm-id{font-size:.75rem}.mm-turnover{font-size:1.6rem}[data-testid="stMetric"]{padding:13px 15px}[data-testid="stMetricValue"]{font-size:1.5rem}}
    </style>""")
    st.html(_navigation_css(collapsed))


def _navigation_css(collapsed):
    """Own the rail geometry; Streamlit's native drawer must not move content.

    The actual controls remain native radio/button widgets with accessible
    names and keyboard navigation. SVGs are decorative local CSS assets.
    """
    icons = [
        '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
        '<path d="m3 6 1.5 1.5L7 5M10 6h11M3 12h3M10 12h11M3 18h3M10 18h11"/>',
        '<circle cx="5" cy="6" r="2.5"/><circle cx="19" cy="6" r="2.5"/><circle cx="12" cy="19" r="2.5"/><path d="M7.5 6h9M6.5 8l4 8.5M17.5 8l-4 8.5"/>',
        '<rect x="3" y="4" width="7" height="6" rx="1.5"/><rect x="14" y="4" width="7" height="6" rx="1.5"/><rect x="8.5" y="16" width="7" height="5" rx="1.5"/><path d="M6.5 10v3H18V10M12 13v3"/>',
        '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Zm0 0v6h6M8 13h8M8 17h6"/>',
        '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 4 16 4 16 0V5M4 12v7c0 4 16 4 16 0v-7"/>',
    ]
    labels = ["Шолу", "Тексеру кезегі", "Желі картасы", "Кластерлер", "Анықтама", "Деректер және экспорт"]

    def svg_url(paths):
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{paths}</svg>'
        return 'url("data:image/svg+xml,' + quote(svg) + '")'

    width = "76px" if collapsed else "264px"
    chevron = '<path d="m9 5 7 7-7 7"/>' if collapsed else '<path d="m15 5-7 7 7 7"/>'
    css = """<style>
    :root { --mm-rail:WIDTH; }
    [data-testid="stSidebar"] {
        position:fixed!important; top:0!important; bottom:0!important; left:0!important;
        width:var(--mm-rail)!important; min-width:var(--mm-rail)!important; max-width:var(--mm-rail)!important;
        height:100dvh!important; transform:none!important; margin:0!important;
        z-index:1000!important; visibility:visible!important; transition:none!important;
        box-shadow:2px 0 12px #102b3c06;
    }
    [data-testid="stSidebarContent"] { width:100%!important; height:100%!important; padding:0!important; overflow-x:hidden; overflow-y:auto; }
    [data-testid="stSidebarUserContent"] { padding:28px 16px 24px!important; width:100%!important; }
    [data-testid="stSidebarHeader"], [data-testid="stSidebarCollapseButton"], [data-testid="stExpandSidebarButton"],
    [data-testid="stSidebar"] > div:nth-child(2) { display:none!important; }
    [data-testid="stMain"] {
        position:absolute!important; left:var(--mm-rail)!important; right:0!important;
        width:calc(100% - var(--mm-rail))!important; margin:0!important; transform:none!important;
        min-width:0!important; transition:none!important;
    }
    [data-testid="stHeader"] { display:none!important; }
    [data-testid="stToolbar"] { display:none!important; }
    .block-container { max-width:1440px; padding:2.3rem 2.2rem 2.5rem; }
    [data-testid="stSidebar"] .stVerticalBlock { gap:0.8rem; }
    .mm-brand { height:40px; gap:10px; margin:0; font-size:1.4rem; }
    .mm-brand-icon { flex:none; width:40px; height:40px; border-radius:11px; }
    .mm-brand-sub { font-size:.6rem; margin:8px 0 0 50px; letter-spacing:.13em; }
    .mm-nav-label { margin:12px 0 0; font-size:.61rem; }
    .st-key-sidebar_toggle { margin:5px 0 2px; }
    .st-key-sidebar_toggle button { width:100%; min-height:36px!important; justify-content:flex-start; gap:10px; padding:6px 11px; box-shadow:none; }
    .st-key-sidebar_toggle button:before { content:''; display:block; flex:none; width:18px; height:18px; background:#aecbd6; mask:CHEVRON center/contain no-repeat; }
    .st-key-sidebar_toggle button p { font-size:.78rem; font-weight:400; color:#aecbd6; }
    [data-testid="stSidebar"] [data-testid="stRadioGroup"] { gap:6px; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] {
        position:relative; display:flex; align-items:center; gap:12px; box-sizing:border-box;
        width:100%!important; min-height:46px; margin:0; padding:10px 12px; border:1px solid transparent;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"]:before {
        content:''; width:21px; height:21px; flex:none; background:#aac6d3;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] { background:#1a494f; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"]:before { background:#78e0c3; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"]:has(input:focus-visible) { outline:2px solid #78e0c3; outline-offset:2px; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] p { white-space:nowrap; font-size:.84rem; }
    .st-key-sidebar_details { margin-top:8px; }
    .st-key-sidebar_details hr { margin:10px 0 20px; }
    .mm-header-meta { padding-top:0; }
    .mm-eyebrow { margin-bottom:7px; }
    .mm-subtitle { margin-bottom:12px; line-height:1.65; }
    [data-testid="stMain"] [data-testid="stCaptionContainer"] p { color:#657b8c; }
    h1 { letter-spacing:-.035em; overflow-wrap:anywhere; }
    .mm-id { overflow-wrap:anywhere; }
    .mm-row > div { min-width:0; }
    .mm-report { white-space:pre-wrap; overflow-wrap:anywhere; font-family:'Segoe UI',Arial,sans-serif; font-size:.9rem; line-height:1.75; color:var(--ink); }
    [data-testid="stMetricValue"] { overflow-wrap:anywhere; }
    @media(max-width:900px) { .block-container { padding:1.8rem 1.3rem 2rem; } }
    @media(max-width:600px) {
        .block-container { padding:1.4rem 1rem 2rem; }
        [data-testid="stColumn"]:has(.mm-header-meta) { display:none; }
        h1 { font-size:1.45rem!important; }
        .mm-eyebrow { letter-spacing:.09em; font-size:.56rem; }
        .mm-subtitle { font-size:.8rem; }
        .mm-turnover { font-size:1.45rem; }
        .mm-welcome { padding:22px; }
        .mm-casebar { gap:5px; padding:6px 0 12px; }
    }
    @media(prefers-reduced-motion:reduce) { *, *:before, *:after { transition:none!important; } }
    """.replace("WIDTH", width).replace("CHEVRON", svg_url(chevron))
    for index, (paths, label) in enumerate(zip(icons, labels), 1):
        selector = f'[data-testid="stSidebar"] [role="radiogroup"] > div:nth-child({index}) [data-testid="stRadioOption"]'
        css += f'{selector}:before {{ mask:{svg_url(paths)} center/contain no-repeat; }}\n'
        if collapsed:
            css += f'{selector}:after {{ content:"{label}" / ""; }}\n'
    if collapsed:
        css += """
        [data-testid="stSidebarUserContent"] { padding:22px 12px!important; }
        [data-testid="stSidebarContent"] { overflow:visible!important; }
        [data-testid="stSidebarUserContent"] > div { overflow:visible!important; }
        .mm-brand { justify-content:center; }
        .mm-brand-name, .mm-brand-sub, .mm-nav-label, .st-key-sidebar_details { display:none!important; }
        .st-key-sidebar_toggle button { min-height:36px!important; justify-content:center; padding:8px; }
        .st-key-sidebar_toggle button [data-testid="stMarkdownContainer"] { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }
        [data-testid="stSidebar"] [data-testid="stRadioOption"] { justify-content:center; padding:11px; min-height:48px; }
        [data-testid="stSidebar"] [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }
        [data-testid="stSidebar"] [data-testid="stRadioOption"]:after {
            display:none; position:absolute; left:61px; top:50%; transform:translateY(-50%);
            white-space:nowrap; color:#183449; background:#fff; border:1px solid #dce6eb;
            padding:8px 12px; border-radius:7px; box-shadow:0 5px 20px #102b3c18;
            font-size:13px; font-weight:500; pointer-events:none; z-index:2000;
        }
        [data-testid="stSidebar"] [data-testid="stRadioOption"]:hover:after,
        [data-testid="stSidebar"] [data-testid="stRadioOption"]:has(input:focus-visible):after { display:block; }
        """
    else:
        # On a phone, opening labels is a deliberate overlay; the workspace
        # keeps the same usable 76px rail inset, never a 264px blank margin.
        css += """
        @media(max-width:600px) {
            [data-testid="stSidebar"] { box-shadow:10px 0 30px #102b3c26; }
            [data-testid="stMain"], [data-testid="stHeader"] { left:76px!important; width:calc(100% - 76px)!important; }
        }
        """
    return css + "</style>"


def badge(text="Жергілікті есептеу"):
    return f'<span class="mm-live">{escape(text)}</span>'


def page_header(title, subtitle):
    left, right = st.columns([4, 1])
    with left:
        st.markdown('<div class="mm-eyebrow">MONEYMAP / ҚАРЖЫЛЫҚ МОНИТОРИНГ</div>', unsafe_allow_html=True)
        st.title(title)
    with right:
        st.markdown(f'<div class="mm-header-meta">{badge()}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="mm-subtitle">{escape(subtitle)}</div>', unsafe_allow_html=True)


def welcome_panel():
    st.markdown('''<div class="mm-welcome"><small>АНАЛИТИКТІҢ ЖҰМЫС КЕҢІСТІГІ</small>
    <h2>Тексеруді маңызды байланыстан бастаңыз.</h2>
    <p>Ақша ағынын зерттеңіз. Клиенттің ықтимал рөлін түсініп, тексеру кезегін нақты деректермен негіздеңіз.</p>
    <div class="mm-pills"><span>Бағытталған граф</span><span>Түсіндірілетін рөлдер</span><span>Жергілікті өңдеу</span></div></div>''', unsafe_allow_html=True)


def guide():
    st.markdown('''<div class="mm-panel-label">ҮШ ҚАДАММЕН НӘТИЖЕГЕ</div>
    <div class="mm-guide"><span>1</span><div><b>Кейсті ашыңыз</b><p>Деректердің құрылымы мен сәйкестігі тексеріледі.</p></div></div>
    <div class="mm-guide"><span>2</span><div><b>Тексеру кезегін дайындаңыз</b><p>Рөлдер, кластерлер және басым клиенттер есептеледі.</p></div></div>
    <div class="mm-guide"><span>3</span><div><b>Байланыс пен дәлелді қараңыз</b><p>Картадан клиентті тауып, негіздемесімен есеп алыңыз.</p></div></div>''', unsafe_allow_html=True)


def candidate_row(rank, gid, label, score):
    st.markdown(f'<div class="mm-row"><span class="mm-rank">{int(rank):02}</span><div><div class="mm-id">{escape(str(gid))}</div><div class="mm-role">{escape(label)}</div></div><span class="mm-score">{float(score):.3f}</span></div>', unsafe_allow_html=True)


def role_distribution(counts, labels):
    for role, label in labels.items():
        st.markdown(f'<div class="mm-role-line"><span class="mm-dot" style="background:{ROLE_COLORS[role]}"></span>{escape(label)}<b>{int(counts.get(role, 0)):,}</b></div>'.replace(",", " "), unsafe_allow_html=True)


def footer():
    st.markdown('<div class="mm-footer"><span>MoneyMap · Қаржылық мониторингке арналған жұмыс кеңістігі</span><span>Рөлдер — тексеру гипотезалары. Шешімді талдаушы қабылдайды.</span></div>', unsafe_allow_html=True)
