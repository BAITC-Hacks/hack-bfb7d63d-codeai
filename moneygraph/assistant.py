"""A deterministic, read-only assistant grounded in the current analysis.

This is intent retrieval, not a language model. Inputs and stored descriptions
are data, never executable instructions. No external services are consulted.
"""

from __future__ import annotations

import math
import re
from typing import Any

ROLE_LABELS = {
    "consolidator": "Жинақтаушы",
    "transit": "Транзит",
    "distributor": "Таратушы",
    "terminal": "Соңғы алушы үміткері",
    "coordinator": "Үйлестіруші үміткері",
    "peripheral": "Рөлі анықталмаған / шеткері",
}
FLAG_LABELS = {
    "boundary_censored": "4-қадамдағы бақылау шекарасы",
    "seed_inflow_incomplete": "бастапқы шоттың кірісі толық емес",
    "outflow_exceeds_observed_inflow": "шығыс көрінетін кірістен жоғары",
    "isolated": "үзіндіде байланыс жоқ",
    "no_observed_outflow": "шығыс аударым көрінбейді",
    "self_transfer": "өзіне аударым бар",
}
FEATURE_LABELS = {
    "betweenness": "жоларалық орталықтық", "observed_volume": "бақыланған ағын",
    "fan_in": "кіріс контрагенттері", "fan_out": "шығыс контрагенттері",
    "pagerank": "PageRank", "community_bridging": "қауымдастық байланыстары",
    "temporal_association": "күндік уақыт сәйкестігі",
}
SUGGESTIONS = ["Кімді бірінші тексеру керек?", "Қай шоттар ақша жинайды?",
               "Қандай дерек жетіспейді?", "Циклдерді көрсет"]
LIMIT_NOTE = "Рөл мен басымдық - тексеру гипотезасы; кінәлілік немесе калибрленген ықтималдық емес."


def identifier(value: Any) -> str:
    """Canonical exact int64 identity; never coerce through floating point."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("gid must be an integer or its exact decimal string")
    if isinstance(value, str) and not re.fullmatch(r"-?\d{1,20}", value.strip()):
        raise ValueError("gid must be an integer or its exact decimal string")
    integer = int(value)
    if not -(2**63) <= integer < 2**63:
        raise ValueError("gid is outside the int64 range")
    return str(integer)


def number(value: Any, digits: int = 0) -> str:
    if value is None or isinstance(value, bool):
        return "дерек жоқ"
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return "дерек жоқ"
    if not math.isfinite(numeric):
        return "дерек жоқ"
    return f"{numeric:,.{digits}f}".replace(",", " ")


def text_data(value: Any, limit: int = 2000) -> str:
    """Bounded source text, with controls stripped; not parsed as instructions."""
    return " ".join(str(value or "").split())[:limit]


def node_index(analysis: dict) -> dict[str, dict]:
    if not isinstance(analysis, dict) or not isinstance(analysis.get("nodes"), list):
        raise ValueError("analysis must contain a nodes list")
    return {identifier(node["gid"]): node for node in analysis["nodes"]}


def get_node(analysis: dict, gid: Any) -> dict:
    key = identifier(gid)
    node = node_index(analysis).get(key)
    if node is None:
        raise ValueError(f"Unknown gid: {key}; no other account was substituted")
    return node


def insight_items(analysis: dict, kind: str, gid: Any = None) -> list[dict]:
    insights = analysis.get("insights") or {}
    if kind in {"cycles", "routes"}:
        records = insights.get(kind) or []
    else:
        accepted = {
            "anomalies": {"peer_outlier", "payment_splitting", "activity_spike"},
            "spikes": {"activity_spike"}, "synchrony": {"synchronized_payers"},
            "forward": {"fast_forward"}, "splitting": {"payment_splitting"},
        }.get(kind, {kind})
        records = [event for event in insights.get("events", []) if event.get("kind") in accepted]
    key = identifier(gid) if gid is not None else None
    return [record for record in records if key is None or key in {identifier(item) for item in record.get("gids", [])}]


def answer_question(analysis: dict, question: str, gid: Any = None) -> dict[str, Any]:
    """Retrieve an answer from analysis only; supports Kazakh/Russian/English intents.

    Response language is Kazakh, matching the application. Unknown explicit
    account IDs and malformed inputs raise ValueError; unsupported topics admit
    the absence of evidence. This function never mutates its inputs.
    """
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError("question must be non-empty text of at most 2000 characters")
    nodes = node_index(analysis)
    context = get_node(analysis, gid) if gid is not None else None
    normalized = question.casefold().replace("ё", "е")
    explicit = re.findall(r"(?:\bgid\b|#|шот|счет|account)\s*[:№#]?\s*(-?\d{1,20})(?!\d)", normalized)
    # Long standalone IDs are unambiguous; short numbers such as "top 5" are not.
    explicit.extend(re.findall(r"(?<![\w-])(-?\d{6,20})(?!\d)", normalized))
    if re.fullmatch(r"\s*-?\d{1,20}\s*", question):
        explicit.append(question.strip())
    keys = list(dict.fromkeys(identifier(item) for item in explicit))
    for key in keys:
        get_node(analysis, key)
    if len(keys) > 1:
        raise ValueError("Ask about one explicit gid at a time")
    if keys:
        context = nodes[keys[0]]
    citations: dict[str, dict] = {}

    def cite(value: Any) -> str:
        key = identifier(value)
        if key in nodes:
            citations[key] = {"gid": nodes[key]["gid"], "label": f"GID {key}"}
        return f"#{key}"

    def result(answer: str, suggestions: list[str] | None = None) -> dict:
        return {"answer": answer, "citations": list(citations.values()),
                "suggestions": suggestions if suggestions is not None else SUGGESTIONS[:], "mode": "local_rules"}

    def contains(*stems: str) -> bool:
        return any(stem in normalized for stem in stems)

    def ranked_candidates(role: str | None = None) -> list[dict]:
        candidates = [node for node in nodes.values() if role is None or node.get("role") == role]
        return sorted(candidates, key=lambda node: (-float(node.get("priority_score") or 0), int(identifier(node["gid"]))))

    # Explicit requests for identity, guilt, or outside records have no backing
    # fields. Never turn a structurally prominent GID into an identified person.
    if contains("жсн", "иин", "iin", "passport", "паспорт", "аты-жөн", "фамили", "кто владелец",
                "real owner", "who owns", "нақты иесі", "кінәлі", "виновен", "criminal name"):
        return result("Бұл талдауда клиенттің аты-жөні, ЖСН, шот иесі немесе кінәлілікті растайтын дерек жоқ. "
                      "Тек иесіздендірілген GID пен бақыланған аударымдарға сүйене аламын.")

    pattern_kind = None
    for candidate, stems in (
        ("cycles", ("цикл", "cycle", "тұйық", "возврат")),
        ("routes", ("маршрут", "route", "бағыт", "қайталан", "цепоч")),
        ("splitting", ("бөлшекте", "дроблен", "split", "structur")),
        ("spikes", ("серпін", "шарық", "всплеск", "spike")),
        ("synchrony", ("синхрон", "synchron", "бір күндегі")),
        ("forward", ("fast", "жылдам", "быстр")),
        ("anomalies", ("аномал", "anomal", "outlier", "ауытқу")),
    ):
        if contains(*stems):
            pattern_kind = candidate
            break
    if pattern_kind:
        records = insight_items(analysis, pattern_kind, context["gid"] if context else None)
        if not records:
            source = "Осы шотқа қатысты " if context else ""
            if context:
                cite(context["gid"])
            return result(source + "сұралған үлгі бойынша сақталған дәлел табылмады. "
                          "Бұл үлгінің нақты жоқ екенін дәлелдемейді; тек есептелген және сақталған нәтижені көрсетемін.")
        lines = [f"Сақталған нәтижелер: {len(records)}. Алғашқы {min(5, len(records))} мысал:"]
        for record in records[:5]:
            refs = [cite(item) for item in record.get("gids", []) if identifier(item) in nodes]
            day = f" · {text_data(record['date'], 30)}" if record.get("date") else ""
            lines.append(f"{text_data(record.get('id'), 80)}{day} · {', '.join(refs)}\n"
                         f"{text_data(record.get('title'), 160)}. Деректегі негіздеме: «{text_data(record.get('evidence'), 600)}»")
        lines.append("Күндік уақыт сәйкестігі бір ақшаның қозғалысын немесе қатысушылардың ортақ бақылауын дәлелдемейді. "
                     "Нәтижелер іздеу шектерімен шектелуі мүмкін; толық шектер analysis.json ішінде.")
        return result("\n\n".join(lines))

    if contains("жетісп", "ақ дақ", "шектеу", "дерек сұра", "не хватает", "пробел", "огранич", "missing", "gap", "next request"):
        if context:
            ref = cite(context["gid"])
            flags = "; ".join(FLAG_LABELS.get(flag, flag) for flag in context.get("flags", [])) or "арнайы белгі жоқ"
            return result(f"{ref}: {flags}.\nКелесі сұрау: {text_data(context.get('next_request')) or 'Қосымша сұрау жазылмаған.'}\n"
                          "Көрінбейтін аударымдарды осы дерекпен қалпына келтіруге болмайды.")
        quality = analysis.get("quality") or {}
        lines = [f"4-қадам шекарасында: {number(quality.get('boundary_nodes'))}; "
                 f"оқшау бастапқы шот: {number(quality.get('isolated_seeds'))}; "
                 f"шығыссыз бастапқы шот: {number(quality.get('seeds_without_outgoing'))}."]
        for request in quality.get("requests", [])[:5]:
            if identifier(request["gid"]) in nodes:
                lines.append(f"{cite(request['gid'])}: {text_data(request.get('request'))}")
        lines.append("Іріктеу кезеңі, 5 000 KZT шегі және тек шығыс бойынша кеңейту толық көріністі шектейді.")
        return result("\n".join(lines))

    if contains("қауымдас", "кластер", "cluster", "сообществ"):
        clusters = analysis.get("clusters") or []
        selected = [c for c in clusters if context is None or c.get("cluster_id") == context.get("cluster_id")]
        selected = sorted(selected, key=lambda c: (-float(c.get("sum_kzt_internal") or 0), c.get("cluster_id", 0)))[:3]
        if context:
            cite(context["gid"])
        lines = []
        for cluster in selected:
            refs = [cite(item) for item in cluster.get("top_gids", []) if identifier(item) in nodes]
            lines.append(f"Қауымдастық {cluster.get('cluster_id')}: {number(cluster.get('n_nodes'))} шот, "
                         f"{number(cluster.get('n_seed'))} бастапқы шот, ішкі бақыланған ағын "
                         f"{number(cluster.get('sum_kzt_internal'), 2)} KZT. Негізгі GID: {', '.join(refs)}.\n"
                         f"Гипотеза: «{text_data(cluster.get('hypothesis'))}»")
        return result("\n\n".join(lines) + "\nҚауымдастық ортақ ұйымның дәлелі емес." if lines else "Сақталған қауымдастық табылмады.")

    requested_role = None
    for role, stems in (
        ("consolidator", ("жинай", "жинақ", "собир", "сборщик", "consolidat", "collect")),
        ("distributor", ("тарат", "распредел", "distribut")),
        ("coordinator", ("үйлест", "координ", "организатор", "coordinat", "organizer")),
        ("terminal", ("соңғы алушы", "конечн", "terminal")),
        ("transit", ("транзит", "transit")),
    ):
        if contains(*stems):
            requested_role = role
            break
    why = contains("неге", "неліктен", "почему", "объясн", "why", "explain", "ұпай", "скор", "score", "рөл", "роль")
    if context and (why or keys or requested_role):
        ref = cite(context["gid"])
        role = ROLE_LABELS.get(context.get("role"), context.get("role", "дерек жоқ"))
        contributions = context.get("priority_contributions") or {}
        factors = sorted(contributions.items(), key=lambda pair: (-float(pair[1]), pair[0]))[:3]
        lines = [f"{ref}: {role}. Басымдық {number(float(context.get('priority_score') or 0) * 100, 1)}/100; "
                 f"рөл белгісінің күші {number(float(context.get('role_score') or 0) * 100, 1)}/100.",
                 f"Кіріс: {number(context.get('in_kzt'), 2)} KZT / {number(context.get('in_tx'))} аударым / "
                 f"{number(context.get('in_degree'))} контрагент. Шығыс: {number(context.get('out_kzt'), 2)} KZT / "
                 f"{number(context.get('out_tx'))} аударым / {number(context.get('out_degree'))} контрагент.",
                 f"Талдаудағы негіздеме (дерек мәтіні): «{text_data(context.get('evidence'))}»"]
        if factors:
            lines.append("Ұпайға үлестер: " + "; ".join(f"{FEATURE_LABELS.get(name, name)} +{number(float(value) * 100, 1)}"
                                                      for name, value in factors) + " / 100.")
        lines.append(LIMIT_NOTE)
        return result("\n\n".join(lines), ["Осы шоттың қауымдастығы", "Қандай дерек жетіспейді?", "Циклдерді көрсет"])

    if requested_role or contains("бірінші", "кімді", "приоритет", "первы", "top", "priority", "ranking", "басымдық"):
        selected = ranked_candidates(requested_role)[:5]
        if not selected:
            return result("Сұралған рөлге сәйкес сақталған түйін жоқ. Рөлді дерексіз тағайындамаймын.")
        lines = []
        for position, node in enumerate(selected, 1):
            lines.append(f"{position}. {cite(node['gid'])} - {ROLE_LABELS.get(node.get('role'), node.get('role'))}; "
                         f"басымдық {number(float(node.get('priority_score') or 0) * 100, 1)}/100. "
                         f"Негіздеме: «{text_data(node.get('evidence'), 350)}»")
        return result("\n\n".join(lines) + "\n\n" + LIMIT_NOTE)

    if contains("жалпы", "қорытынды", "обзор", "итог", "summary", "overview"):
        meta = analysis.get("meta") or {}
        return result(f"Бақыланған желі: {number(meta.get('n_nodes'))} шот, {number(meta.get('n_edges'))} бағытталған байланыс, "
                      f"{number(meta.get('n_transactions'))} аударым, {number(meta.get('n_seeds'))} бастапқы шот. "
                      f"Кезең: {text_data(meta.get('period_start'))} - {text_data(meta.get('period_end'))}. "
                      f"Жиынтық бақыланған ағын: {number(meta.get('total_kzt'), 2)} KZT. " + LIMIT_NOTE)
    if why:
        return result("Нақты шоттың рөлі мен ұпайын түсіндіру үшін GID жазыңыз немесе графтан шот таңдаңыз.")
    return result("Бұл сұраққа ағымдағы талдауда жеткілікті дәлел жоқ. Мен жергілікті ережелік көмекшімін: "
                  "сақталған шоттарды, рөлдерді, ұпайларды, қауымдастықтарды, үлгілерді және дерек шектерін түсіндіремін. "
                  "Сыртқы фактілерді немесе клиент сипаттарын ойдан қоспаймын.")
