"""Local, explainable anomaly signals with explicit coverage and parameters."""

import hashlib
import json
import math

import pandas as pd
import streamlit as st

from moneymap.anomalies import SIGNAL_LABELS, analyze_anomalies
from moneymap.graph import analyze_dataset


DIRECTION_LABELS = {"incoming": "Кіріс", "outgoing": "Шығыс"}
STATUS_LABELS = {
    "coverage_excluded": "Бақылау толық емес: салыстыруға алынбады",
    "small_group": "Клиент саны жеткіліксіз",
    "zero_robust_scale": "Медианалық ауытқу нөлге жуық: ұпай есептелмеді",
    "evaluated": "Салыстырылды",
}


def _fingerprint(frames):
    digest = hashlib.sha256()
    for name in ("nodes", "edges", "transactions"):
        digest.update(name.encode())
        digest.update(pd.util.hash_pandas_object(frames[name], index=True).to_numpy().tobytes())
    return digest.hexdigest()


def _discard_results():
    for key in ("anomaly_result", "anomaly_result_signature", "anomaly_result_params"):
        st.session_state.pop(key, None)


def _can_reuse_graph(graph, frames):
    """Reuse only matching graph inputs; this tab never changes shared results."""
    if graph is None:
        return False
    columns = ["gid", "depth", "is_seed"]
    expected = frames["nodes"][columns].sort_values("gid", kind="stable").reset_index(drop=True)
    actual = graph.nodes[columns].sort_values("gid", kind="stable").reset_index(drop=True)
    if not actual.equals(expected) or graph.graph.number_of_edges() != len(frames["edges"]):
        return False
    for src, dst, amount, n_tx in frames["edges"][["src", "dst", "sum_kzt", "n_tx"]].itertuples(index=False, name=None):
        edge = graph.graph.get_edge_data(int(src), int(dst))
        if edge is None or edge["n_tx"] != n_tx or not math.isclose(edge["sum_kzt"], amount, abs_tol=0.01, rel_tol=0):
            return False
    transactions = frames["transactions"]
    if not transactions.empty:
        if (graph.summary.get("min_date") != transactions["date"].min().strftime("%Y-%m-%d")
                or graph.summary.get("max_date") != transactions["date"].max().strftime("%Y-%m-%d")):
            return False
    return True


def render_anomalies_tab(validation):
    st.subheader("Әдеттен тыс үлгілерді тексеру")
    st.write("Ұқсас сомалар, күндік белсенділіктің өсуі, бір күндегі бірнеше жіберуші және өз буынындағы көлем айырмасы. Әр белгіге нақты сандар мен есептеу шарты беріледі.")
    st.caption("Бұл — қосымша тексеруге арналған белгілер. Олар кінәлілікті немесе оның ықтималдығын көрсетпейді; рөлдер мен тексеру басымдығын өзгертпейді.")
    if not validation.valid:
        _discard_results()
        st.info("Алдымен деректердегі қателерді түзетіңіз.")
        return
    signature = _fingerprint(validation.frames)
    if st.session_state.get("anomaly_result_signature", signature) != signature:
        _discard_results()

    with st.expander("Тексеру параметрлері", expanded=False):
        reference_enabled = st.checkbox("Нақты үлгі соманың айналасынан іздеу", key="anomaly_use_reference")
        cols = st.columns(3)
        reference = cols[0].number_input("Үлгі сома, ₸", min_value=0.01, value=10000.0, step=1000.0, disabled=not reference_enabled, key="anomaly_reference_amount")
        tolerance = cols[1].number_input("Сомалар айырмасына төзім, %", min_value=0.0, max_value=100.0, value=5.0, step=1.0, key="anomaly_tolerance_pct")
        repeat_min = cols[2].number_input("Ұқсас аударымдар минимумы", min_value=2, value=3, step=1, key="anomaly_repeat_min")
        st.caption("Үлгі сома қосылмаса, бір жіберушінің бір күндегі ең көп қайталанған тар сома аралығы ізделеді: ең үлкен сома ≤ ең кіші сома × (1 + төзім). Үлгі сома қосылса, екі жаққа да сол пайыз қолданылады. Бұл заңдық шек емес.")
        cols = st.columns(3)
        spike_min = cols[0].number_input("Өсу белгісі үшін күндік операция минимумы", min_value=2, value=5, step=1, key="anomaly_spike_min")
        spike_ratio = cols[1].number_input("Қалған күндерге қатысты өсу, есе", min_value=1.01, value=3.0, step=0.5, key="anomaly_spike_ratio")
        min_days = cols[2].number_input("Күндік салыстыруға қажет кезең, күн", min_value=3, value=7, step=1, key="anomaly_min_days")
        cols = st.columns(3)
        sync_min = cols[0].number_input("Бір күндегі әртүрлі жіберуші минимумы", min_value=2, value=3, step=1, key="anomaly_sync_min")
        peer_min = cols[1].number_input("Бір буындағы салыстыру тобының минимумы", min_value=5, value=10, step=1, key="anomaly_peer_min")
        peer_z = cols[2].number_input("Медианадан стандартталған ауытқу минимумы", min_value=0.1, value=3.5, step=0.5, key="anomaly_peer_z")
        max_alerts = st.number_input("Көрсету және жүктеу үшін жол шегі", min_value=1, max_value=10000, value=1000, step=100, key="anomaly_max_alerts")
        st.caption("Буын ішіндегі салыстыру log(1 + көлем), медиана және медианалық абсолюттік ауытқуды қолданады. Топ шағын немесе ауытқу нөлге жуық болса, ұпай ойдан жасалмайды: салыстыру өткізіледі.")

    parameters = {
        "reference_amount": reference if reference_enabled else None, "amount_tolerance": tolerance / 100,
        "repeat_min_tx": repeat_min, "spike_min_tx": spike_min, "spike_ratio": spike_ratio,
        "min_observation_days": min_days, "sync_min_payers": sync_min,
        "peer_min_size": peer_min, "peer_z_threshold": peer_z, "max_alerts": max_alerts,
    }
    if st.button("Үлгілерді есептеу", key="anomaly_compute", type="primary"):
        _discard_results()
        with st.spinner("Транзакциялардан түсіндірілетін белгілер есептеліп жатыр…"):
            try:
                graph = st.session_state.get("analysis")
                if not _can_reuse_graph(graph, validation.frames):
                    graph = analyze_dataset(validation.frames)
                result = analyze_anomalies(graph, validation.frames["transactions"], **parameters)
                st.session_state.anomaly_result = result
                st.session_state.anomaly_result_signature = signature
                st.session_state.anomaly_result_params = parameters
            except (ValueError, RuntimeError) as error:
                st.error(f"Белгілерді есептеу аяқталмады: {error}")
    result = st.session_state.get("anomaly_result")
    if result is None:
        st.info("Параметрлерді тексеріп, үлгілерді есептеңіз. Деректер осы компьютерде өңделеді.")
        return
    if st.session_state.get("anomaly_result_params") != parameters:
        st.info("Параметрлер өзгерді. Жаңартылған нәтижені алу үшін қайта есептеңіз.")
        return

    summary = result.summary
    st.success(f"Табылған белгілер: {summary['alerts_detected']} · көрсетілгені: {summary['alerts_returned']}")
    period = summary["observation_period"]
    st.caption(f"Бақылау: {period['first_date'] or '—'} — {period['last_date'] or '—'} · {period['calendar_days']} күн. Өзіне аударымдардан шығарылғаны: {summary['excluded_self_transfers']}. Файлда 5 000 ₸-ден төмен операция: {summary['observed_below_case_sampling_floor']}.")
    if summary["alerts_truncated"]:
        st.warning("Жол шегіне жетті. Ережелер толық есептелді, бірақ кесте мен CSV тек алғашқы жолдарды қамтиды. Көрсету реті қауіп дәрежесі емес; қажет болса жол шегін арттырыңыз.")
    if not summary["spikes_evaluated"]:
        st.info("Күндік өсу белгісіне бақылау кезеңі қысқа. Қалған ережелер қолжетімді дерекпен есептелді.")
    if summary["spike_zero_baseline_node_days_skipped"]:
        st.caption(f"Қалған күндерде операция болмағандықтан, өсу қатынасы есептелмеген жағдай: {summary['spike_zero_baseline_node_days_skipped']}.")
    counts = pd.DataFrame({"Белгі": [SIGNAL_LABELS[key] for key in SIGNAL_LABELS], "Табылғаны": [summary["signal_counts"][key] for key in SIGNAL_LABELS]})
    st.dataframe(counts, hide_index=True, width="stretch")
    if result.alerts.empty:
        st.info("Осы шарттармен белгі табылмады. Бұл клиенттердің қауіпсіздігі туралы қорытынды емес.")
    else:
        _render_alerts(result)
    with st.expander("Өткізілген салыстырулар және дерек шектеулері"):
        if summary["peer_groups"]:
            groups = pd.DataFrame(summary["peer_groups"])
            groups["direction"] = groups["direction"].map(DIRECTION_LABELS)
            groups["status"] = groups["status"].map(STATUS_LABELS)
            st.dataframe(groups, hide_index=True, width="stretch", column_config={
                "depth": "Буын", "direction": "Бағыт", "n_peers": "Клиент саны", "status": "Нәтиже",
                "median_log": "Логарифм медианасы", "mad_log": "Медианалық ауытқу", "scale_log": "Салыстыру масштабы",
            })
        for item in result.limitations:
            st.write(f"• {item}")
    st.download_button("Белгілер мен дәлелдер · CSV", result.alerts.to_csv(index=False).encode("utf-8-sig"), file_name="observed-anomaly-signals.csv", mime="text/csv", key="anomaly_download_csv")
    st.download_button("Параметрлер мен шектеулер · JSON", json.dumps({"summary": summary, "limitations": result.limitations}, ensure_ascii=False, indent=2, allow_nan=False), file_name="anomaly-analysis-report.json", mime="application/json", key="anomaly_download_report")
    st.caption("CSV импорттағанда gid бағанын мәтін ретінде таңдаңыз. Әр белгі бөлек жол: бір клиент бірнеше рет кездесе алады.")


def _render_alerts(result):
    selected = st.selectbox("Белгі түрі", ["all", *SIGNAL_LABELS], format_func=lambda key: "Барлығы" if key == "all" else SIGNAL_LABELS[key], key="anomaly_signal_filter")
    alerts = result.alerts if selected == "all" else result.alerts.loc[result.alerts["signal"].eq(selected)]
    shown = alerts[["gid", "signal", "direction", "date", "n_tx", "sum_kzt", "explanation"]].copy()
    shown["signal"] = shown["signal"].map(SIGNAL_LABELS)
    shown["direction"] = shown["direction"].map(DIRECTION_LABELS)
    st.dataframe(shown, hide_index=True, width="stretch", column_config={
        "gid": st.column_config.TextColumn("Клиент gid"), "signal": "Белгі", "direction": "Бағыт", "date": "Күн",
        "n_tx": "Операциялар", "sum_kzt": st.column_config.NumberColumn("Бақыланған сома, ₸", format="%.2f"), "explanation": "Есептеу негізі",
    })
    if alerts.empty:
        return
    index = st.selectbox("Белгінің толық негізі", alerts.index.tolist(), format_func=lambda value: f"{result.alerts.at[value, 'gid']} · {SIGNAL_LABELS[result.alerts.at[value, 'signal']]} · {result.alerts.at[value, 'date'] or 'толық кезең'}", key="anomaly_detail")
    row = result.alerts.loc[index]
    st.info(row["explanation"])
    st.caption(row["caveats"])
    unit = {"similar_amounts": "ұқсас операция саны", "daily_spike": "өсу қатынасы", "same_day_payers": "әртүрлі жіберуші саны", "depth_peer_outlier": "стандартталған ауытқу"}[row["signal"]]
    st.write(f"**Салыстырылған көрсеткіш:** {float(row['statistic']):.4f} ({unit}) · **шарт:** ≥{float(row['threshold']):g}.")
    if row["signal"] == "depth_peer_outlier":
        st.caption(f"Салыстыру тобы: {int(row['peer_n'])} клиент; log(1 + көлем) медианасы: {float(row['peer_median_log']):.6f}; медианалық абсолюттік ауытқу: {float(row['peer_mad_log']):.6f}.")
