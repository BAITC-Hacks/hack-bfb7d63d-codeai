"""Local investigation aids built from the same validated graph and role results."""

import pandas as pd
import streamlit as st

from moneymap.graph import analyze_dataset
from moneymap.investigation import analyze_routes, node_briefing, resilience_analysis
from moneymap.network_insights import analyze_network, compare_removal_strategies
from moneymap.roles import classify_graph
from moneymap.ui_state import clear_investigation_state
from moneymap.extended_reports import extended_export_files
from moneymap.reports import role_export_zip


def render_investigation_tab(validation):
    st.subheader("Қосымша талдау")
    st.write("Клиент туралы қысқа анықтама, қайталанатын маршруттар және желінің құрылымдық тұрақтылығы.")
    if not validation.valid:
        st.info("Қосымша талдау үшін алдымен деректердегі қателерді түзетіңіз.")
        return
    if st.button("Қосымша талдауды дайындау", key="inv_prepare", type="primary"):
        clear_investigation_state()
        with st.spinner("Граф пен тексеру басымдығы дайындалып жатыр…"):
            try:
                graph = st.session_state.get("analysis")
                if graph is None:
                    graph = analyze_dataset(validation.frames)
                    st.session_state.analysis = graph
                if st.session_state.get("role_analysis") is None:
                    st.session_state.role_analysis = classify_graph(graph)
                st.session_state.inv_ready = True
            except (ValueError, RuntimeError) as error:
                st.error(f"Талдау дайындалмады: {error}")
    if not st.session_state.get("inv_ready"):
        st.info("Батырма қажет граф пен рөлдерді автоматты түрде есептейді. Талдау осы компьютерде орындалады.")
        return

    graph = st.session_state.analysis
    roles = st.session_state.role_analysis
    if st.button("Қосымша есептердің бәрін дайындау", key="inv_export_all"):
        with st.spinner("Маршруттар, аномалиялар және дерек сұраулары дайындалып жатыр…"):
            st.session_state.inv_export_zip = role_export_zip(extended_export_files(graph, roles, validation.frames))
    if "inv_export_zip" in st.session_state:
        st.download_button("Қосымша есептер · ZIP", st.session_state.inv_export_zip, file_name="moneymap-extended.zip", mime="application/zip", key="inv_download_all")
        st.caption("Бұл жинақ әдепкі талдау шектерімен жасалады; шектер JSON есебінде жазылған. Сарапшы бағасының үлгісі бос күйде беріледі.")
    brief_tab, routes_tab, resilience_tab, flow_tab, coverage_tab = st.tabs([
        "Клиент анықтамасы", "Маршруттар мен циклдер", "Желі тұрақтылығы", "Топтар арасындағы ағын", "Дерек толықтығы",
    ])
    with brief_tab:
        _render_brief(graph, roles)
    with routes_tab:
        _render_routes(graph, validation.frames["transactions"])
    with resilience_tab:
        _render_resilience(graph, roles)
    if "inv_network" not in st.session_state:
        st.session_state.inv_network = analyze_network(graph, roles)
    with flow_tab:
        _render_network(st.session_state.inv_network)
    with coverage_tab:
        _render_coverage(st.session_state.inv_network)


def _render_brief(graph, roles):
    ranked = roles.details.sort_values(
        ["priority_score", "in_kzt", "gid"], ascending=[False, False, True], kind="stable",
    )
    gid = st.selectbox("Анықтама үшін клиент · gid", [str(int(value)) for value in ranked.gid], key="inv_gid")
    brief = node_briefing(graph, gid, roles=roles)
    st.markdown(brief.text)
    st.markdown("**Нені нақтылау керек**")
    for item in brief.limitations:
        st.write(f"• {item}")
    st.markdown("**Келесі дерек сұраулары**")
    for item in brief.next_requests:
        st.write(f"• {item}")
    st.caption("Анықтама есептелген фактілер мен ашық ережелерден жергілікті құрастырылады. AI моделі қолданылмайды.")
    document = (
        brief.text + "\n\n## Нені нақтылау керек\n\n"
        + "\n".join(f"- {item}" for item in brief.limitations)
        + "\n\n## Келесі дерек сұраулары\n\n"
        + "\n".join(f"- {item}" for item in brief.next_requests)
    )
    st.download_button("Анықтаманы жүктеу · Markdown", document, file_name=f"client-{gid}.md", mime="text/markdown", key="inv_download_brief")


def _render_routes(graph, transactions):
    st.write("Бағытталған циклдер мен екі бағыттағы аударымдар құрылымдық байланыстарды көрсетеді. Қайталанатын A → B → C маршруты кемінде екі бөлек кіріс күнінде, кейінгі 1–2 күндік шығыспен ізделеді.")
    window = st.selectbox("Маршруттың уақыт аралығы, күн", [1, 2], index=1, key="inv_window")
    if st.button("Маршруттарды тексеру", key="inv_compute_routes"):
        with st.spinner("Циклдер мен күндер бойынша қайталанулар тексеріліп жатыр…"):
            st.session_state.inv_routes = analyze_routes(graph, transactions, window_days=window)
            st.session_state.inv_routes_window = window
    result = st.session_state.get("inv_routes")
    if result is None or st.session_state.get("inv_routes_window") != window:
        st.info("Таңдалған уақыт аралығымен маршруттарды тексеріңіз.")
        return

    summary = result.summary
    st.success(f"Циклдер: {len(result.cycles)} · екі бағытты жұптар: {len(result.reciprocal)} · қайталанатын маршруттар: {len(result.routes)}")
    if any(summary.get(key, False) for key in ("cycles_truncated", "route_search_truncated", "routes_truncated")):
        st.warning("Іздеу немесе көрсету шегіне жетті. Кестелер барлық маршрут пен циклді қамтымайды; төмендегі есеп шектерін қараңыз.")
    st.markdown("**Қайталанатын маршруттар**")
    if result.routes.empty:
        st.info("Осы іздеу шегінде кемінде екі бөлек күнде қайталанған маршрут табылмады.")
    else:
        st.dataframe(result.routes, hide_index=True, width="stretch", column_config={
            "src": "Жіберуші", "via": "Аралық клиент", "dst": "Алушы", "path": "Маршрут",
            "eligible_in_days": "Бақылауы жеткілікті кіріс күндері", "matched_in_days": "Шығыс байқалған кіріс күндері",
            "matched_in_tx": "Сәйкес кіріс операциялары", "first_in_date": "Алғашқы кіріс күні", "last_in_date": "Соңғы кіріс күні",
            "min_lag_days": "Ең қысқа аралық, күн", "max_lag_days": "Ең ұзақ аралық, күн",
        })
    st.markdown("**Қайтарма бағыттағы жұптар**")
    if result.reciprocal.empty:
        st.info("Бақыланған графта екі бағыттағы жұптар табылмады.")
    else:
        st.dataframe(result.reciprocal, hide_index=True, width="stretch", column_config={
            "src": "Бірінші клиент", "dst": "Екінші клиент", "forward_kzt": "Алға, ₸", "reverse_kzt": "Кері, ₸",
            "forward_tx": "Алға операциялар", "reverse_tx": "Кері операциялар",
        })
    st.markdown("**Бағытталған циклдер**")
    if result.cycles.empty:
        st.info("Осы іздеу шегінде қысқа бағытталған циклдер табылмады.")
    else:
        st.dataframe(result.cycles, hide_index=True, width="stretch", column_config={
            "path": "Цикл", "n_edges": "Байланыс саны", "observed_edge_turnover_kzt": "Байланыстардың жиынтық айналымы, ₸",
        })
    for item in result.limitations:
        st.caption(item)
    with st.expander("Іздеу шектері мен есеп"):
        st.json(summary)
    for name, frame in (("repeated_routes", result.routes), ("cycles", result.cycles), ("reciprocal_pairs", result.reciprocal)):
        st.download_button(f"{name} · CSV", frame.to_csv(index=False).encode("utf-8-sig"), file_name=f"{name}.csv", mime="text/csv", key=f"inv_download_{name}")


def _render_resilience(graph, roles):
    st.write("Басымдығы жоғары N клиентті және олардың байланыстарын графтан алып тастағандағы құрылымды салыстырыңыз. Бұл — талдау сценарийі; клиент шоттарына еш әрекет жасалмайды.")
    ranked = roles.details.sort_values(
        ["priority_score", "in_kzt", "gid"], ascending=[False, False, True], kind="stable",
    )
    top_n = st.number_input("Алып тасталатын басым клиент саны", min_value=1, max_value=len(ranked), value=min(5, len(ranked)), step=1, key="inv_top_n")
    if st.button("Сценарийді есептеу", key="inv_compute_resilience"):
        st.session_state.inv_resilience = resilience_analysis(graph, ranked.gid.tolist(), top_n=top_n)
        st.session_state.inv_resilience_n = top_n
        st.session_state.inv_strategy_comparison = compare_removal_strategies(graph, roles, top_n=top_n)
    result = st.session_state.get("inv_resilience")
    if result is None or st.session_state.get("inv_resilience_n") != top_n:
        st.info("Клиент санын таңдап, сценарийді есептеңіз.")
        return

    comparison = result.comparison.set_index("scenario")
    rows = []
    for column, label, number_format in (
        ("n_nodes", "Клиенттер", ",.0f"), ("n_edges", "Байланыстар", ",.0f"),
        ("weak_components", "Бөліктер", ",.0f"), ("largest_component_nodes", "Ең үлкен бөлік", ",.0f"),
        ("largest_component_share", "Бөлік үлесі", ".1%"),
        ("observed_edge_turnover_kzt", "Айналым, ₸", ",.2f"),
        ("retained_turnover_share", "Қалған айналым", ".1%"),
    ):
        values = [comparison.loc[scenario, column] for scenario in ("before", "after")]
        formatted = ["—" if pd.isna(value) else format(value, number_format).replace(",", " ") for value in values]
        rows.append({"Көрсеткіш": label, "Дейін": formatted[0], "Кейін": formatted[1]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Ең үлкен бөліктің үлесі — сол сценарийде қалған клиенттерден; айналым үлесі — бастапқы байланыстар айналымынан есептеледі.")
    with st.expander(f"Сценарийден алынған клиенттер · {len(result.removed_gids)}"):
        st.write(", ".join(result.removed_gids))
    for item in result.limitations:
        st.caption(item)
    st.download_button("Тұрақтылық есебі · CSV", result.comparison.to_csv(index=False).encode("utf-8-sig"), file_name="network-resilience.csv", mime="text/csv", key="inv_download_resilience")
    strategies, metadata = st.session_state.inv_strategy_comparison
    st.markdown("**Басым клиенттер мен бастапқы тізімге әсер етуді салыстыру**")
    st.caption(metadata["note"])
    if metadata["compared_n"]:
        st.caption(f"Әр стратегияда {metadata['compared_n']} клиент алынады. Сұралған саны: {metadata['requested_n']}.")
        st.dataframe(strategies, hide_index=True, width="stretch")
        st.download_button("Стратегияларды салыстыру · CSV", strategies.to_csv(index=False).encode("utf-8-sig"), file_name="removal-strategies.csv", mime="text/csv", key="inv_download_strategies")
    else:
        st.info("Бастапқы клиенттер жоқ: екі стратегияны салыстыру мүмкін емес.")


def _render_network(result):
    st.write("Ақша қай топтан қай топқа өтетінін және топтарды байланыстыратын клиенттерді қараңыз.")
    st.metric("Топтар арасындағы бақыланған айналым, ₸", f"{result.summary['external_turnover_kzt']:,.2f}".replace(",", " "))
    st.dataframe(result.flows, hide_index=True, width="stretch", column_config={
        "src_cluster": "Жіберуші топ", "dst_cluster": "Алушы топ", "sum_kzt": "Айналым, ₸", "n_tx": "Операциялар", "n_edges": "Байланыстар",
    })
    st.markdown("**Топтарды байланыстырушы клиенттер**")
    st.dataframe(result.bridges, hide_index=True, width="stretch", column_config={
        "rank": "Реті", "gid": "Клиент", "neighbor_clusters": "Өзге топтар", "external_neighbors": "Өзге топтағы клиенттер", "evidence": "Негізі",
        "is_articulation": "Алынса бөлік бөлшектенеді", "external_turnover_kzt": "Топаралық айналым, ₸",
    })
    for item in result.limitations[:4]:
        st.caption(item)
    for name, label, frame in (("cluster_flows", "Топаралық ағын", result.flows), ("bridge_nodes", "Байланыстырушы клиенттер", result.bridges)):
        st.download_button(f"{label} · CSV", frame.to_csv(index=False).encode("utf-8-sig"), file_name=f"{name}.csv", mime="text/csv", key=f"inv_download_{name}")


def _render_coverage(result):
    st.write("Әр клиентке қатысты бақылау шектеулері және оларды нақтылауға арналған дерек сұраулары.")
    st.info(result.limitations[-1])
    display = result.coverage.copy()
    names = {"seed_incoming_incomplete": "Бастапқы клиенттің кірісі толық емес", "outgoing_beyond_boundary_unknown": "4-қадамнан кейінгі шығыс белгісіз", "no_observed_links": "Бақыланған байланыс жоқ", "outgoing_exceeds_observed_incoming": "Шығыс көрінетін кірістен артық", "no_additional_node_specific_flag": "Қосымша жеке белгі жоқ; жалпы шектеулер сақталады"}
    display["specific_gaps"] = display["specific_gaps"].map(lambda value: "; ".join(names[flag] for flag in value.split("|")))
    display["coverage_status"] = "Толық қамтылуы белгісіз"
    st.dataframe(display, hide_index=True, width="stretch", column_config={
        "gid": "Клиент", "specific_gaps": "Клиентке тән шектеулер", "coverage_status": "Толық қамтылу", "min_observed_seed_hops": "Seed-тен ең қысқа қадам",
    })
    titles = {"boundary_outgoing": "Төртінші қадамнан кейінгі аударымдар", "seed_incoming": "Бастапқы клиенттердің кірісі", "isolated_clients": "Байланысы көрінбейтін клиенттер", "sampling_scope": "Іріктеу ауқымы", "expert_review": "Сарапшының тексеруі"}
    for row in result.requests.to_dict("records"):
        with st.expander(f"{titles[row['request_id']]} · {row['affected_nodes']} клиент"):
            st.write(row["reason"])
            st.write(row["request"])
            st.text(row["gids"])
    for name, frame in (("node_coverage", result.coverage), ("data_requests", result.requests)):
        st.download_button(f"{name} · CSV", frame.to_csv(index=False).encode("utf-8-sig"), file_name=f"{name}.csv", mime="text/csv", key=f"inv_download_{name}")
