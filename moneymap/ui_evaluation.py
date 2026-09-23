"""Kazakh analyst-review UI; labels live only in the current Streamlit session."""

import streamlit as st

from moneymap.evaluation import (
    UNKNOWN, dataset_fingerprint, evaluate_reviews, make_review,
    ranked_gids, read_review_csv, review_csv,
)
from moneymap.graph import analyze_dataset
from moneymap.roles import ROLE_LABELS, ROLE_ORDER, classify_graph


def _bind_dataset(fingerprint):
    if st.session_state.get("eval_dataset_sha256") != fingerprint:
        for key in list(st.session_state):
            if key.startswith("eval_"):
                st.session_state.pop(key, None)
        st.session_state.eval_dataset_sha256 = fingerprint
        st.session_state.eval_reviews = {}


def _clear_editor():
    for key in list(st.session_state):
        if key.startswith("eval_editor_"):
            st.session_state.pop(key, None)


def _percentage(value):
    return "—" if value is None else f"{value:.1%}"


def render_evaluation_tab(validation):
    st.subheader("Сарапшы бағалауы")
    st.write("Өзіңіз тексерген рөлдер мен тексеру қажеттілігін белгілеңіз. Жүйе сарапшы белгілерін болжамнан автоматты түрде жасамайды.")
    if not validation.valid:
        st.info("Бағалау үшін алдымен бастапқы деректердегі қателерді түзетіңіз.")
        return
    fingerprint = dataset_fingerprint(validation.frames)
    _bind_dataset(fingerprint)
    st.caption("Белгілер осы сессияның жадында сақталады. Бетті қайта ашар алдында CSV жүктеп алыңыз. Деректер ауысса белгілер тазартылады; бір деректегі рөлдерді қайта есептеу оларды сақтайды.")
    if st.button("Сарапшы тексеруін дайындау", key="eval_prepare", type="primary"):
        with st.spinner("Клиенттер мен ағымдағы болжамдар дайындалып жатыр…"):
            try:
                if st.session_state.get("analysis") is None:
                    st.session_state.analysis = analyze_dataset(validation.frames)
                if st.session_state.get("role_analysis") is None:
                    st.session_state.role_analysis = classify_graph(st.session_state.analysis)
                st.session_state.eval_ready = True
            except (ValueError, RuntimeError) as error:
                st.error(f"Бағалау дайындалмады: {error}")
    roles = st.session_state.get("role_analysis")
    if not st.session_state.get("eval_ready") or roles is None:
        st.info("Тексеру кестесін дайындаңыз. Белгіленбеген клиенттер теріс жауап болып саналмайды.")
        return

    predictions = roles.details
    ordered = ranked_gids(predictions)
    if not ordered:
        st.info("Бағалайтын клиент жоқ.")
        return
    k = int(st.number_input("Басымдықты бағалау: алғашқы k клиент", min_value=1, max_value=len(ordered),
                            value=min(20, len(ordered)), step=1, key="eval_k"))
    with st.expander("CSV үлгісі, импорт және белгілерді сақтау", expanded=True):
        selection = st.radio("Үлгіге кіретін клиенттер", ["Барлық клиенттер", "Алғашқы k клиент"],
                             horizontal=True, key="eval_template_scope")
        selected = ordered if selection == "Барлық клиенттер" else ordered[:k]
        st.download_button("Бос тексеру үлгісін жүктеу · CSV", review_csv(predictions, fingerprint, gids=selected),
                           file_name="expert-review-template.csv", mime="text/csv", key="eval_download_template")
        st.caption("gid бағанын кестелік редакторда мәтін ретінде ашыңыз: ұзын идентификатор өзгермеуі керек. reviewed_role: алты рөл немесе unknown; investigation_relevant: true / false / unknown. Болжам бағандары сарапшы жауабынан бөлек. Ескертпедегі формула таңбалары экспортта қорғалады.")
        upload = st.file_uploader("Толтырылған тексеру CSV", type=["csv"], key="eval_upload")
        st.caption("Импорттағы жолдар сол клиенттердің сессиядағы белгілерін алмастырады; файлда жоқ клиенттер сақталады. Басқа деректер жиынының файлы қабылданбайды.")
        if st.button("CSV белгілерін қолдану", key="eval_import"):
            if upload is None:
                st.info("Алдымен толтырылған CSV файлын таңдаңыз.")
            else:
                try:
                    imported = read_review_csv(upload.getvalue(), predictions, fingerprint)
                    st.session_state.eval_reviews = {**st.session_state.eval_reviews, **imported}
                    _clear_editor()
                    st.success(f"Қабылданған жолдар: {len(imported)}. Файлдағы бұрынғы болжамдар бағалауға көшірілмейді; ағымдағы болжам қолданылады.")
                except ValueError as error:
                    st.error(f"Импорт қабылданбады; бұрынғы белгілер сақталды. {error}")

    gid = st.selectbox("Тексерілетін клиент · gid", ordered, key="eval_gid")
    row = predictions.loc[predictions.gid.map(lambda value: str(int(value))).eq(gid)].iloc[0]
    st.write(f"**Жүйенің болжамы:** {ROLE_LABELS[row.role]} · рөл ұпайы {row.role_score:.3f} · тексеру басымдығы {row.priority_score:.3f}.")
    st.caption("Төмендегі сарапшы жауабы осы болжамнан тәуелсіз сақталады. «Белгісіз» жауабы сапа метрикасының бөліміне кірмейді.")
    saved = st.session_state.eval_reviews.get(gid, make_review(fingerprint, gid))
    role_choices = [UNKNOWN, *ROLE_ORDER]
    relevance_choices = [UNKNOWN, "true", "false"]
    relevance_labels = {UNKNOWN: "Әлі анықталмаған", "true": "Қосымша тексеруге қажет", "false": "Осы тексеру мақсаты үшін қажет емес"}
    with st.form("eval_review_form"):
        reviewed_role = st.selectbox("Сарапшы анықтаған рөл", role_choices,
                                     index=role_choices.index(saved.reviewed_role),
                                     format_func=lambda role: "Белгісіз / әлі бағаланбаған" if role == UNKNOWN else ROLE_LABELS[role],
                                     key=f"eval_editor_role_{gid}")
        relevance = st.selectbox("Қосымша тексеру қажеттілігі", relevance_choices,
                                 index=relevance_choices.index(saved.investigation_relevant),
                                 format_func=relevance_labels.get, key=f"eval_editor_relevance_{gid}")
        note = st.text_area("Сарапшының негіздемесі", value=saved.reviewer_note, max_chars=2000,
                            key=f"eval_editor_note_{gid}")
        if st.form_submit_button("Сарапшы белгісін сақтау", key="eval_save"):
            try:
                review = make_review(fingerprint, gid, reviewed_role, relevance, note)
                st.session_state.eval_reviews = {**st.session_state.eval_reviews, gid: review}
                st.success("Сарапшы белгісі сессияға сақталды.")
            except ValueError as error:
                st.error(str(error))

    reviews = st.session_state.eval_reviews
    annotated_ids = [gid for gid in ordered if gid in reviews]
    st.download_button("Сақталған белгілерді жүктеу · CSV", review_csv(predictions, fingerprint, reviews, annotated_ids),
                       file_name="expert-reviews.csv", mime="text/csv", key="eval_download_reviews", disabled=not annotated_ids)
    result = evaluate_reviews(predictions, fingerprint, reviews, k=k)
    summary = result.summary
    st.warning("Көрсеткіштер тек сарапшы белгісі бар осы шағын іріктемеге қатысты. Іріктеме бүкіл желіні сипаттамауы мүмкін; бұл толық шынайы рөлдер базасы, ұпай калибровкасы немесе кінәлілікті анықтау сапасы емес.")
    st.markdown("**Рөлдердің сарапшы жауабымен сәйкестігі**")
    st.write(f"Белгілі рөлмен бағаланғаны: **{summary['role_reviewed_n']} / {summary['n_nodes']}** ({summary['role_coverage']:.1%}). Дұрыс сәйкес келгені: **{summary['role_correct_n']}**.")
    columns = st.columns(2)
    columns[0].metric("Осы іріктемедегі accuracy", _percentage(summary["accuracy"]))
    columns[1].metric("Осы іріктемедегі macro F1", _percentage(summary["macro_f1"]))
    if summary["role_reviewed_n"]:
        st.caption("Қателер матрицасы: жол — сарапшы рөлі, баған — ағымдағы болжам. Macro F1 сарапшы жауабында немесе осы бағаланған жолдардың болжамында кездескен рөлдерден орташа алынады: " + ", ".join(summary["macro_f1_labels"]) + ".")
        st.dataframe(result.confusion, width="stretch")
        st.dataframe(result.by_role, hide_index=True, width="stretch")
    else:
        st.info("Белгілі рөлмен бағаланған клиент жоқ; accuracy және F1 есептелген жоқ.")
    st.markdown(f"**Алғашқы {summary['actual_k']} клиенттің тексеруге жарамдылығы**")
    st.write(f"Қажеттілігі анықталған: **{summary['relevance_assessed_n']} / {summary['actual_k']}** ({summary['relevance_coverage']:.1%}); тексеруге қажет: **{summary['relevant_n']}**; анықталмаған: **{summary['unassessed_n']}**.")
    st.write(f"Тек бағаланғандардың ішіндегі үлес: **{_percentage(summary['assessed_precision_at_k'])}** = {summary['relevant_n']} / {summary['relevance_assessed_n']}." if summary["relevance_assessed_n"] else "Тексеру қажеттілігі әлі бағаланбаған; бағаланғандар үлесі есептелмейді.")
    if summary["precision_at_k"] is not None:
        st.metric(f"Толық бағаланған алғашқы {summary['actual_k']} үшін precision@k", _percentage(summary["precision_at_k"]))
    else:
        st.info(f"Толық precision@k есептелмейді: анықталмағандар бар. Мүмкін аралық: {_percentage(summary['precision_at_k_lower_bound'])}–{_percentage(summary['precision_at_k_upper_bound'])}; бөлім — алғашқы {summary['actual_k']} клиенттің бәрі.")
    st.dataframe(result.ranking, hide_index=True, width="stretch")
    with st.expander("Деректердің сәйкестік белгісі"):
        st.code(fingerprint, language=None)
        st.caption("SHA256 үш кестенің міндетті мәндерінен есептеледі; жол реті өзгерсе сақталады, транзакциялар мен олардың қайталану саны өзгерсе ауысады. Жазбалар сервер дискісіне автоматты түрде жазылмайды.")
