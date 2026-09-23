"""Explicit AI assistance with a useful local mode and server-only credentials."""

import hashlib
from html import escape
import json
from pathlib import Path
import re

import pandas as pd
import streamlit as st

from moneymap.ai_budget import AIBudgetError, BudgetLedger
from moneymap.ai_facts import build_evidence, local_report
from moneymap.ai_provider import AIProviderError
from moneymap.ai_response import AIResponseError
from moneymap.ai_service import request_analysis
from moneymap.ai_settings import AIConfigError, load_settings
from moneymap.graph import analyze_dataset
from moneymap.roles import classify_graph
from moneymap.ui_state import clear_ai_state, queue_map_navigation


ROOT = Path(__file__).resolve().parents[1]
TASKS = {
    "report_client": "Талдаушыға қысқа анықтама",
    "explain_client": "Рөл мен басымдықтың толық негізі",
    "top_priority": "Кімді алдымен тексеру керек?",
    "cluster_summary": "Кластерді түсіндіру",
    "common_recipients": "Ортақ алушыларды табу",
}


def _render_report(text):
    """Display literal report text with readable typography; never interpret it as HTML."""
    with st.container(border=True):
        st.markdown(f'<div class="mm-report">{escape(text)}</div>', unsafe_allow_html=True)


def render_ai_tab(validation):
    if not validation.valid:
        st.info("Алдымен деректерді тексеріп, қателерін түзетіңіз.")
        return
    ready = st.session_state.get("ai_ready", False)
    preparation = st.expander("Анықтама деректерін жаңарту", expanded=False) if ready else st.container()
    with preparation:
        if ready:
            st.caption("Ағымдағы анықтама тазартылып, осы кейстің есептелген көрсеткіштері қайта қолданылады. API сұрауы жіберілмейді.")
        prepare_clicked = st.button("Деректерді қайта дайындау" if ready else "Көмекшіге деректерді дайындау", key="prepare_ai", type="secondary" if ready else "primary")
    if prepare_clicked:
        clear_ai_state()
        with st.spinner("Жергілікті граф пен рөлдер дайындалып жатыр…"):
            try:
                if st.session_state.get("analysis") is None:
                    st.session_state.analysis = analyze_dataset(validation.frames)
                if st.session_state.get("role_analysis") is None:
                    st.session_state.role_analysis = classify_graph(st.session_state.analysis)
                st.session_state.ai_ready = True
            except Exception:
                st.error("Деректерді дайындау аяқталмады. Граф пен рөлдерді қайта есептеңіз.")
    if not st.session_state.get("ai_ready"):
        st.info("Жоғарыдағы батырма жергілікті деректерді дайындайды. API кілті қажет емес және сұрау жіберілмейді.")
        return
    analysis, roles = st.session_state.analysis, st.session_state.role_analysis
    task = st.selectbox("Анықтама түрі", list(TASKS), format_func=TASKS.get, key="ai_task")
    arguments = {}
    if task in ("explain_client", "report_client"):
        gids = [str(int(gid)) for gid in roles.details.sort_values(["priority_score", "gid"], ascending=[False, True]).gid]
        preferred = st.session_state.get("map_selected_gid")
        arguments["gid"] = st.selectbox("Түсіндіретін клиент · gid", gids,
                                       index=gids.index(preferred) if preferred in gids else 0, key="ai_gid")
    elif task == "top_priority":
        arguments["top_n"] = st.slider("Клиент саны", min_value=1, max_value=10, value=5, key="ai_top_n")
    elif task == "cluster_summary":
        arguments["cluster_id"] = st.selectbox("Түсіндіретін кластер", roles.clusters.cluster_id.tolist(), key="ai_cluster")
    else:
        entered = st.text_area("Салыстыратын клиенттер · 2–5 gid", key="ai_gids", placeholder="Әр gid-ті жаңа жолға жазыңыз немесе үтірмен бөліңіз.")
        arguments["gids"] = [value for value in re.split(r"[\s,;]+", entered.strip()) if value]
    try:
        bundle = build_evidence(analysis, roles, task, **arguments)
    except (ValueError, TypeError, KeyError):
        st.info("Осы тапсырма үшін деректердегі жарамды клиенттерді таңдаңыз. Ортақ алушыларға 2–5 әртүрлі gid қажет.")
        return

    actions = st.container()
    report_area = st.container()
    facts_area = st.container()
    with st.expander("Қосымша: LLM түсіндірмесі және баптаулар", expanded=False):
        st.caption("Бұл қосымша режим. Негізгі анықтама, рөлдер және тексеру кезегі API-сыз жұмыс істейді. Тірі провайдер сапасы бөлек тексеруді қажет етеді.")
        provider = st.selectbox("AI провайдері", ["openai", "nvidia"], format_func={"openai": "OpenAI", "nvidia": "NVIDIA"}.get, key="ai_provider")
        settings = None
        try:
            settings = load_settings(provider, root=ROOT)
        except AIConfigError as exc:
            st.error(str(exc))
        if settings:
            status = "қосылған" if settings.ready else "өшірулі / кілт жоқ"
            st.caption(f"{provider.upper()} · {settings.model} · API {status}")
            st.caption(f"Жоба лимиті: {settings.max_requests} сұрау, {settings.max_total_tokens:,} токен; OpenAI есептік шығын шегі ${settings.budget_usd:.2f}. Бұл аккаунт балансы емес.")
        st.write("Қосу үшін сервердегі .env файлына OPENAI_API_KEY не NVIDIA_API_KEY енгізіп, MONEYMAP_AI_ENABLED=true орнатыңыз. Кілттер интерфейсте көрсетілмейді.")
        st.button("API күйін жаңарту", key="ai_refresh")
        st.caption("NVIDIA режимі API Catalog токеніне арналған. Модельге қысқаша қаржылық көрсеткіштер мен C001 сияқты белгілер жіберіледі; бастапқы Parquet пен gid сәйкестігі жіберілмейді.")
        generate_clicked = st.button("AI түсіндірмесін алу", key="ai_generate", disabled=not (settings and settings.ready), width="stretch")
        st.caption("Модель мәтіні фактілердің мағынасын бұрмалауы мүмкін. Нәтижені бастапқы деректермен тексеріңіз; факт нөмірі тұжырымның дұрыстығын дәлелдемейді.")
        usage_area = st.container()
    signature = hashlib.sha256(f"{bundle.fingerprint}:{provider}:{settings.model if settings else ''}".encode()).hexdigest()
    if st.session_state.get("ai_output_signature") != signature:
        st.session_state.pop("ai_output", None)
        st.session_state.pop("ai_error", None)
        st.session_state.ai_output_signature = signature
    with actions:
        columns = st.columns([2, 1]) if "gid" in arguments else [st.container()]
        with columns[0]:
            local_clicked = st.button("Анықтаманы дайындау · API-сыз", key="ai_local", type="primary", width="stretch")
        if "gid" in arguments:
            with columns[1]:
                if st.button("Картадан тексеру", key="ai_open_map", width="stretch"):
                    queue_map_navigation(gid=str(arguments["gid"]))
    if local_clicked:
        st.session_state.ai_output = {"report": local_report(bundle), "local": True, "origin": "explicit_local"}
        st.session_state.pop("ai_error", None)
    if generate_clicked:
        st.session_state.pop("ai_output", None)
        st.session_state.pop("ai_error", None)
        with st.spinner("Таңдалған провайдер фактілерді түсіндіріп жатыр…"):
            try:
                ledger = BudgetLedger(ROOT / "output" / "ai" / "usage.sqlite3")
                st.session_state.ai_output = request_analysis(settings, bundle, cache=st.session_state.setdefault("ai_cache", {}), ledger=ledger)
            except (AIProviderError, AIResponseError, AIBudgetError) as exc:
                st.session_state.ai_error = str(exc)
                st.session_state.ai_output = {"report": local_report(bundle), "local": True, "origin": "api_fallback"}
            except Exception:
                st.session_state.ai_error = "AI сұрауы аяқталмады. Автоматты қайталау жасалмады; жергілікті есеп төменде қолжетімді."
                st.session_state.ai_output = {"report": local_report(bundle), "local": True, "origin": "api_fallback"}
    with report_area:
        if st.session_state.get("ai_error"):
            st.warning(st.session_state.ai_error)
        output = st.session_state.get("ai_output")
        if output:
            if output.get("local"):
                if output.get("origin") == "explicit_local":
                    st.success("Жергілікті анықтама дайын · API сұрауы жіберілген жоқ")
                else:
                    st.info("Жергілікті анықтама дайын. Алдыңғы API әрекетінің шығыны болуы мүмкін; күйін қосымша баптаудағы журналдан тексеріңіз.")
                _render_report(output["report"])
            else:
                st.success("Кэштен алынды · жаңа сұрау жоқ" if output["from_cache"] else "LLM түсіндірмесі алынды · талдаушы тексеруі қажет")
                _render_report(local_report(bundle))
                with st.expander("LLM мәтіні · автоматты расталмаған түсіндірме", expanded=False):
                    _render_report(output["report"])
                    st.caption(f"Кіріс токендері: {output['input_tokens'] if output['input_tokens'] is not None else 'белгісіз'} · Шығыс токендері: {output['output_tokens'] if output['output_tokens'] is not None else 'белгісіз'}")
            st.download_button("Анықтаманы жүктеу · TXT", output["report"].encode("utf-8-sig"), file_name="moneymap-analytical-note.txt", mime="text/plain", key="ai_download_report")
    with facts_area:
        with st.expander("Нақты фактілер және есептеу өрістері", expanded=False):
            st.caption("F нөмірі жергілікті есептелген мәнге сілтейді. Операцияларды клиенттің картадағы карточкасынан тексеруге болады.")
            st.dataframe(pd.DataFrame([{"Белгі": alias, "gid": gid} for alias, gid in bundle.aliases.items()]), hide_index=True, width="stretch")
            display_facts = [{**fact, "value": str(fact["value"])} for fact in bundle.facts]
            st.dataframe(pd.DataFrame(display_facts), hide_index=True, width="stretch")
            st.download_button("Жергілікті фактілер · JSON", json.dumps({**bundle.public_payload(), "aliases": bundle.aliases}, ensure_ascii=False, indent=2), file_name="moneymap-evidence.json", mime="application/json", key="ai_download_facts")
    with usage_area:
        path = ROOT / "output" / "ai" / "usage.sqlite3"
        if path.exists():
            try:
                st.json(BudgetLedger(path).stats())
            except Exception:
                st.warning("Жергілікті шығын журналы оқылмады. Жаңа сұрауды қоспас бұрын файлды тексеріңіз.")
        else:
            st.caption("Бұл жобада API сұраулары әлі тіркелмеген.")
        st.caption("Журнал сұрау, токен және есептік шығынды сақтайды; клиент деректері мен кілттер жазылмайды. Қабылданбаған жауап та токен жұмсауы мүмкін. Қатеден кейін автоматты қайта сұрау жоқ.")
