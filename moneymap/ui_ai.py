"""Explicit AI assistance with a useful local mode and server-only credentials."""

import hashlib
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
from moneymap.graph_questions import answer_question, GraphQuestionError, MAX_QUESTION_CHARS
from moneymap.roles import classify_graph
from moneymap.ui_state import clear_ai_state


ROOT = Path(__file__).resolve().parents[1]
TASKS = {
    "explain_client": "Клиент неге маңызды?",
    "report_client": "Клиент туралы анықтама",
    "top_priority": "Кімді алдымен тексеру керек?",
    "cluster_summary": "Кластерді түсіндіру",
    "common_recipients": "Ортақ алушыларды табу",
}


def _text_question(analysis, roles):
    st.caption("Қазақша немесе орысша бір сұрақ жазыңыз. Бұл — шектеулі жергілікті сұрақ талдағышы: клиент, топ-1–10, кластер, ортақ алушылар, seed жолдары, кіріс/шығыс және дерек толықтығы. Күн/сома сүзгілері мен еркін күрделі сұрақтар қолдау таппайды.")
    sample = [str(int(gid)) for gid in roles.details.sort_values("gid").gid[:2]]
    with st.expander("Қолдау бар сұрақтардың үлгілері"):
        examples = [
            f"Неге gid {sample[0]} маңызды?",
            "Алдымен тексеретін топ 5 клиент",
            f"Объясни кластер {int(roles.clusters.cluster_id.iloc[0])}",
            f"Seed-тен gid {sample[0]}-ке жол",
            f"Кімге gid {sample[0]} ақша жіберді?",
            f"Каких данных не хватает для gid {sample[0]}?",
        ]
        if len(sample) > 1:
            examples.append(f"{sample[0]} және {sample[1]} ортақ алушыларын көрсет")
        st.text("\n".join(examples))
        st.caption("Жауап толық жүктелген кезеңге сүйенеді. Жолдар — құрылымдық байланыстар, рөлдер — тексеру гипотезалары. Түсініксіз сұраққа жауап ойдан жасалмайды.")
    question = st.text_area("Граф туралы сұрағыңыз", max_chars=MAX_QUESTION_CHARS, key="ai_question", placeholder=examples[0])
    fingerprint = hashlib.sha256(question.encode("utf-8")).hexdigest()
    if st.session_state.get("ai_question_fingerprint") != fingerprint:
        for key in ("ai_question_bundle", "ai_question_error", "ai_output", "ai_error", "ai_output_signature"):
            st.session_state.pop(key, None)
        st.session_state.ai_question_fingerprint = fingerprint
    submitted = st.button("Сұраққа жауап беру · API-сыз", key="ai_ask_question", type="primary")
    if submitted:
        for key in ("ai_question_bundle", "ai_question_error", "ai_output", "ai_error"):
            st.session_state.pop(key, None)
        try:
            st.session_state.ai_question_bundle = answer_question(analysis, roles, question)
        except GraphQuestionError as exc:
            st.session_state.ai_question_error = str(exc)
        except (ValueError, TypeError, KeyError):
            st.session_state.ai_question_error = "Сұрақтағы клиент не кластер осы деректерге сәйкес келмейді. Идентификаторды тексеріңіз немесе дайын тапсырманы таңдаңыз."
    if st.session_state.get("ai_question_error"):
        st.info(st.session_state.ai_question_error)
    bundle = st.session_state.get("ai_question_bundle")
    if bundle is not None:
        st.caption("Танылған тапсырма: " + bundle.title + ". Сұрақ мәтіні провайдерге жіберілмейді; қосымша AI түсіндірмесі тек төмендегі фактілерге сүйенеді.")
    return bundle, submitted


def render_ai_tab(validation):
    st.subheader("AI көмекші")
    st.write("Дайын фактілерді түсіндіру және аналитикалық анықтама. Сандарды Python есептейді; AI мәтінді құрастырады.")
    if not validation.valid:
        st.info("Алдымен деректерді тексеріп, қателерін түзетіңіз.")
        return
    if st.button("Көмекшіге деректерді дайындау", key="prepare_ai", type="primary"):
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
    mode = st.radio("Сұрақ беру тәсілі", ["Дайын тапсырма", "Сұрақ жазу"], horizontal=True, key="ai_mode")
    question_submitted = False
    if mode == "Сұрақ жазу":
        bundle, question_submitted = _text_question(analysis, roles)
        if bundle is None:
            return
    else:
        task = st.selectbox("Көмекшіге тапсырма", list(TASKS), format_func=TASKS.get, key="ai_task")
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

    provider = st.selectbox("AI провайдері", ["openai", "nvidia"], format_func={"openai": "OpenAI", "nvidia": "NVIDIA"}.get, key="ai_provider")
    settings = None
    try:
        settings = load_settings(provider, root=ROOT)
    except AIConfigError as exc:
        st.error(str(exc))
    if settings:
        status = "қосылған" if settings.ready else "өшірулі / кілт жоқ"
        st.caption(f"{provider.upper()} · {settings.model} · API {status}")
        st.caption(f"Жоба лимиті: {settings.max_requests} сұрау, {settings.max_total_tokens:,} токен; OpenAI есептік шығын шегі ${settings.budget_usd:.2f}. Бұл API аккаунтыңыздың балансы емес.")
    with st.expander("API кілтін кейін қалай қосамын?"):
        st.write("Кілттерді осы компьютердегі .env файлына енгізіңіз. Кілтті чатқа не Git-ке қоспаңыз. Сайт кілттің мәнін көрсетпейді.")
        st.code(str(ROOT / ".env"), language=None)
        st.code("OPENAI_API_KEY=өзіңіздің_кілтіңіз\n# Немесе NVIDIA_API_KEY=өзіңіздің_кілтіңіз\nMONEYMAP_AI_ENABLED=true", language="dotenv")
        st.write("Файлды сақтап, төмендегі «API күйін жаңарту» батырмасын басыңыз. Сұрау тек «AI түсіндірмесін алу» басылғанда жіберіледі. Екі провайдердің біреуін таңдаңыз.")
        st.button("API күйін жаңарту", key="ai_refresh")
        st.caption("NVIDIA нұсқасы API Catalog токеніне арналған. Басқа сервистің токені болса, оның қосылу мекенжайын алдымен нақтылау қажет.")

    with st.expander("Түсіндіруге дайын фактілер", expanded=False):
        st.caption("Толық gid сәйкестігі тек осы компьютерде қалады. Модельге C001 сияқты уақытша белгілер және төмендегі таңдалған көрсеткіштер жіберіледі.")
        st.dataframe(pd.DataFrame([{"Белгі": alias, "gid": gid} for alias, gid in bundle.aliases.items()]), hide_index=True, width="stretch")
        display_facts = [{**fact, "value": str(fact["value"])} for fact in bundle.facts]
        st.dataframe(pd.DataFrame(display_facts), hide_index=True, width="stretch")
        st.download_button("Жергілікті фактілер · JSON", json.dumps({**bundle.public_payload(), "aliases": bundle.aliases}, ensure_ascii=False, indent=2), file_name="moneymap-evidence.json", mime="application/json", key="ai_download_facts")
    st.caption("AI сұрауы таңдалған провайдерге осы тапсырманың қысқаша қаржылық көрсеткіштерін жібереді. Бастапқы Parquet файлдары мен gid сәйкестік кестесі жіберілмейді.")
    signature = hashlib.sha256(f"{mode}:{bundle.fingerprint}:{provider}:{settings.model if settings else ''}".encode()).hexdigest()
    if st.session_state.get("ai_output_signature") != signature:
        st.session_state.pop("ai_output", None)
        st.session_state.pop("ai_error", None)
        st.session_state.ai_output_signature = signature
    if question_submitted:
        st.session_state.ai_output = {"report": local_report(bundle), "local": True}
    left, right = st.columns(2)
    if left.button("Жергілікті есепті ашу · API-сыз", key="ai_local", width="stretch"):
        st.session_state.ai_output = {"report": local_report(bundle), "local": True}
        st.session_state.pop("ai_error", None)
    if right.button("AI түсіндірмесін алу", key="ai_generate", disabled=not (settings and settings.ready), type="primary", width="stretch"):
        st.session_state.pop("ai_output", None)
        st.session_state.pop("ai_error", None)
        with st.spinner("Таңдалған провайдер фактілерді түсіндіріп жатыр…"):
            try:
                ledger = BudgetLedger(ROOT / "output" / "ai" / "usage.sqlite3")
                st.session_state.ai_output = request_analysis(settings, bundle, cache=st.session_state.setdefault("ai_cache", {}), ledger=ledger)
            except (AIProviderError, AIResponseError, AIBudgetError) as exc:
                st.session_state.ai_error = str(exc)
                st.session_state.ai_output = {"report": local_report(bundle), "local": True}
            except Exception:
                st.session_state.ai_error = "AI сұрауы аяқталмады. Автоматты қайталау жасалмады; жергілікті есеп төменде қолжетімді."
                st.session_state.ai_output = {"report": local_report(bundle), "local": True}
    if st.session_state.get("ai_error"):
        st.warning(st.session_state.ai_error)
    output = st.session_state.get("ai_output")
    if output:
        if output.get("local"):
            st.success("Жергілікті есеп дайын · AI қолданылған жоқ · API шығыны жоқ")
        else:
            cached = "Кэштен алынды · жаңа сұрау жоқ" if output["from_cache"] else "AI жауабы алынды"
            st.success(cached)
            st.caption(f"Кіріс токендері: {output['input_tokens'] if output['input_tokens'] is not None else 'белгісіз'} · Шығыс токендері: {output['output_tokens'] if output['output_tokens'] is not None else 'белгісіз'}")
        st.text(output["report"])
        st.download_button("Анықтаманы жүктеу · TXT", output["report"].encode("utf-8-sig"), file_name="moneymap-analytical-note.txt", mime="text/plain", key="ai_download_report")
    with st.expander("Шығын есебі және жауаптың шектеулері"):
        path = ROOT / "output" / "ai" / "usage.sqlite3"
        if path.exists():
            try:
                st.json(BudgetLedger(path).stats())
            except Exception:
                st.warning("Жергілікті шығын журналы оқылмады. Жаңа сұрауды қоспас бұрын файлды тексеріңіз.")
        else:
            st.caption("Бұл жобада API сұраулары әлі тіркелмеген.")
        st.write("Журналда сұрау саны, токендер және есептік шығын ғана сақталады. Кілттер мен клиент деректері журналға жазылмайды. Белгісіз шығын үшін алдын ала резерв сақталады; қатеден кейін автоматты қайта сұрау немесе басқа провайдерге ауысу жоқ.")
        st.write("Сандар модельдің мәтінінен алынбайды: Python бастапқы фактілерді тіркейді. Жауап схемасы, фактілерге сілтемелер және клиент белгілері тексеріледі. Мәтіннің мағынасы толық автоматты дәлелденбейді — талдаушы қарауы керек. Рөл — тексеру гипотезасы.")
