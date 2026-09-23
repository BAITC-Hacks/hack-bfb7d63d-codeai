"""Bounded local evidence for AI explanations, without transmitting client IDs.

Only whitelisted computed values enter public payloads. Free-form evidence,
cluster hypotheses, transaction rows and private alias maps are never included.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import numbers

import pandas as pd

from moneymap.data import _exact_integer
from moneymap.graph import AnalysisResult, observed_seed_paths
from moneymap.roles import ROLE_LABELS, RoleAnalysis


TASKS = {"explain_client", "report_client", "top_priority", "cluster_summary", "common_recipients",
         "seed_paths", "data_completeness", "client_flows"}
BASE_WARNINGS = [
    "Көрсеткіштер толық бақыланған жиыннан жергілікті есептелген; карта сүзгілері оларды өзгертпейді.",
    "Жіберушілер мен алушылар саны тек өзге клиенттерді қамтиды. Өзіне аударымдар сомалар мен операциялар санында сақталады.",
    "Рөлдер мен басымдық — тексеру болжамдары; ұпай кінәлілік ықтималдығы емес.",
    "Байланыс пен жақын сомалар дәл сол қаражаттың өткенін немесе операциялардың уақыт ретін дәлелдемейді.",
    "Seed клиенттерінің кірісі толық емес; олардың шығыс/кіріс қатынасы рөлге дәлел болмайды.",
    "4-буынның кейінгі шығысы шектеулі: шығыстың жоқтығы соңғы алушы екенін дәлелдемейді.",
]
CLIENT_FIELDS = (
    ("role_score", "Рөл ережесіне сәйкестік", "ұпай"),
    ("priority_score", "Тексеру басымдығы", "ұпай"),
    ("cluster_id", "Кластер нөмірі", ""),
    ("depth", "Буын", "қадам"),
    ("is_seed", "Бастапқы клиент", ""),
    ("is_isolated", "Бақыланған байланысы жоқ", ""),
    ("truncated_by_depth", "Шығыс бақылауы 4-буынмен шектелген", ""),
    ("in_kzt", "Кіріс сомасы", "₸"),
    ("out_kzt", "Шығыс сомасы", "₸"),
    ("in_deg", "Өзге бірегей жіберушілер", "клиент"),
    ("out_deg", "Өзге бірегей алушылар", "клиент"),
    ("in_tx", "Кіріс операциялары", "операция"),
    ("out_tx", "Шығыс операциялары", "операция"),
    ("reachable_seed_count", "Бағытталған жолмен жететін өзге seed", "клиент"),
    ("min_seed_hops", "Seed-тен ең аз қадам", "қадам"),
    ("pagerank", "PageRank", ""),
    ("betweenness", "Аралық орталықтық", ""),
    ("observed_flow_ratio", "Бақыланған шығыс/кіріс", "қатынас"),
    ("ratio_usable", "Қатынас рөл ережесіне жарамды", ""),
    ("active_days", "Белсенді күндер", "күн"),
    ("in_active_days", "Кірісі бар күндер", "күн"),
    ("out_active_days", "Шығысы бар күндер", "күн"),
    ("first_date", "Алғашқы белсенді күн", ""),
    ("last_date", "Соңғы белсенді күн", ""),
    ("mean_next_out_days", "Кейінгі шығысқа дейінгі шартты орташа күн", "күн"),
    ("next_out_1_2d_share", "Кейінгі 1–2 күнде шығыс байқалған кірістер үлесі", "үлес"),
    ("temporal_eligible_in_tx", "Уақыттық үлестің кіріс операциялар саны", "операция"),
    ("priority_consolidation", "Басымдық үлесі: жинақталу", "ұпай"),
    ("priority_in_kzt", "Басымдық үлесі: кіріс сомасы", "ұпай"),
    ("priority_in_deg", "Басымдық үлесі: жіберушілер", "ұпай"),
    ("priority_betweenness", "Басымдық үлесі: аралық орталықтық", "ұпай"),
    ("priority_seed_reach", "Басымдық үлесі: seed-тен жету", "ұпай"),
    ("priority_out_deg", "Басымдық үлесі: алушылар", "ұпай"),
    ("priority_pagerank", "Басымдық үлесі: PageRank", "ұпай"),
)


@dataclass
class EvidenceBundle:
    task: str
    title: str
    facts: list[dict]
    warnings: list[str]
    aliases: dict[str, str]

    def public_payload(self) -> dict:
        """Return an independent provider-safe copy, without private gids."""
        return deepcopy({"task": self.task, "title": self.title, "facts": self.facts, "warnings": self.warnings})

    @property
    def fingerprint(self) -> str:
        # Private aliases participate so identical numeric evidence belonging
        # to different clients cannot reuse one another's cached explanations.
        serialized = json.dumps({**self.public_payload(), "aliases": self.aliases}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _scalar(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value
    raise ValueError("Дәлел мәні JSON скаляр түрінде болуы керек")


def _gid(value, available) -> int:
    try:
        parsed = _exact_integer(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("gid дәл int64 бүтін саны болуы керек") from exc
    if parsed not in available:
        raise ValueError("Көрсетілген gid деректер жиынында жоқ")
    return parsed


def _rows(analysis, roles) -> dict[int, dict]:
    tables = (analysis.nodes, roles.nodes_roles, roles.details)
    if any("gid" not in table or not table.gid.is_unique for table in tables):
        raise ValueError("Клиенттер мен рөлдер бірегей gid арқылы берілуі керек")
    metrics, labels, details = [{int(row["gid"]): row for row in table.to_dict("records")} for table in tables]
    if not metrics or any(set(rows) != set(analysis.graph) for rows in (metrics, labels, details)):
        raise ValueError("Граф пен рөлдер бір толық деректер жиынына тиесілі болуы керек")
    for gid in metrics:
        if any(not isinstance(row.get("role"), str) or row["role"] not in ROLE_LABELS for row in (labels[gid], details[gid])):
            raise ValueError("Белгісіз рөл мәні")
        for row in (labels[gid], details[gid]):
            for key in ("role_score", "priority_score"):
                score = row.get(key)
                if isinstance(score, bool) or not isinstance(score, numbers.Real) or not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Рөл мен басымдық ұпайлары 0–1 аралығындағы шекті сан болуы керек")
        if any(details[gid].get(key) != labels[gid].get(key) for key in ("role", "role_score", "priority_score", "cluster_id")):
            raise ValueError("Рөл кестелері өзара сәйкес емес")
        if any(details[gid].get(key) != metrics[gid].get(key) for key in ("in_kzt", "out_kzt", "in_deg", "out_deg", "in_tx", "out_tx", "depth", "is_seed")):
            raise ValueError("Рөл көрсеткіштері графқа сәйкес емес; рөлдерді қайта есептеңіз")
    return {gid: {**details[gid], **metrics[gid], **labels[gid]} for gid in sorted(metrics)}


def build_evidence(
    analysis: AnalysisResult,
    roles: RoleAnalysis,
    task: str,
    *,
    gid=None,
    cluster_id=None,
    gids=None,
    top_n=5,
    direction="both",
) -> EvidenceBundle:
    """Build <=100 scalar facts; common recipients are direct intersections.

    Shared recipients exclude every selected sender, including self transfers.
    Ranking uses actual selected-sender incoming sum, then gid, with at most 10
    recipients. Cluster summaries contain at most five priority-ranked members.
    """
    if not isinstance(task, str) or task not in TASKS:
        raise ValueError("Белгісіз талдау тапсырмасы")
    if isinstance(top_n, bool) or not isinstance(top_n, numbers.Integral) or not 1 <= top_n <= 10:
        raise ValueError("top_n 1–10 аралығындағы бүтін сан болуы керек")
    if direction not in ("both", "incoming", "outgoing") or (task != "client_flows" and direction != "both"):
        raise ValueError("Бағыт тек client_flows тапсырмасы үшін incoming/outgoing/both болады")
    rows = _rows(analysis, roles)
    facts, aliases = [], {}
    reverse_aliases = {}
    warnings = BASE_WARNINGS.copy()

    def alias(client):
        if client not in reverse_aliases:
            key = f"C{len(aliases) + 1:03d}"
            aliases[key] = str(client)
            reverse_aliases[client] = key
        return reverse_aliases[client]

    def add(label, value, unit="", source="graph"):
        facts.append({"id": f"F{len(facts) + 1:03d}", "label": label, "value": _scalar(value), "unit": unit, "source": source})

    def node_fact(client, key, label, unit=""):
        source = "roles." + key if key in ("role", "role_score", "cluster_id", "priority_score") or key.startswith("priority_") else "graph." + key
        value = ROLE_LABELS[rows[client]["role"]] if key == "role" else rows[client][key]
        add(f"{alias(client)} · {label}", value, unit, source)

    def ranked(members):
        return sorted(members, key=lambda client: (-float(rows[client]["priority_score"]), -float(rows[client]["in_kzt"]), client))

    def compact_client(client, rank):
        add(f"{alias(client)} · Тексеру кезегі", rank, "орын", "roles.priority_order")
        for key, label, unit in (
            ("role", "Рөл болжамы", ""), ("priority_score", "Тексеру басымдығы", "ұпай"),
            ("in_kzt", "Кіріс сомасы", "₸"), ("in_deg", "Өзге бірегей жіберушілер", "клиент"),
            ("out_deg", "Өзге бірегей алушылар", "клиент"), ("depth", "Буын", "қадам"), ("is_seed", "Бастапқы клиент", ""),
        ):
            node_fact(client, key, label, unit)

    for key, label, unit in (
        ("nodes", "Бақыланған клиенттер", "клиент"), ("edges", "Бағытталған байланыстар", "байланыс"),
        ("transactions", "Бақыланған операциялар", "операция"), ("seeds", "Бастапқы клиенттер", "клиент"),
        ("turnover_kzt", "Жиынның бақыланған айналымы", "₸"),
        ("min_date", "Бақылау кезеңінің басы", ""), ("max_date", "Бақылау кезеңінің соңы", ""),
    ):
        add(label, analysis.summary.get(key), unit, "dataset." + key)

    if task in ("explain_client", "report_client"):
        if cluster_id is not None or gids is not None:
            raise ValueError("Клиент тапсырмасына тек gid беріледі")
        client = _gid(gid, rows)
        title = f"{alias(client)} клиентінің " + ("түсіндірмесі" if task == "explain_client" else "аналитикалық есебі")
        node_fact(client, "role", "Рөл болжамы")
        for key, label, unit in CLIENT_FIELDS:
            node_fact(client, key, label, unit)
        warnings.append("Уақыттық үлеске соңғы екі күннің кірістері кірмейді; сол күнгі аударым реті анықталмайды. Орташа күн тек кейінгі шығысы байқалған кірістерге шартты есептеледі.")
        if rows[client]["is_isolated"]:
            warnings.append(f"{alias(client)}: бақыланған аударым жоқ; бұл қауіпсіздік туралы қорытынды емес.")
        elif rows[client]["self_loop_only"]:
            warnings.append(f"{alias(client)}: тек өзіне аударым байқалған; өзге клиентпен байланыс жоқ. Рөлге дәлел жеткіліксіз.")
    elif task in ("seed_paths", "client_flows", "data_completeness"):
        if cluster_id is not None or gids is not None:
            raise ValueError("Осы тапсырмаға тек бір gid беріледі")
        client = _gid(gid, rows) if gid is not None else None
        if task != "data_completeness" and client is None:
            raise ValueError("Осы тапсырмаға gid қажет")
        if client is not None:
            alias(client)
            for key, label, unit in (
                ("in_kzt", "Бақыланған толық кіріс", "₸"),
                ("out_kzt", "Бақыланған толық шығыс", "₸"),
                ("in_tx", "Кіріс операциялары", "операция"),
                ("out_tx", "Шығыс операциялары", "операция"),
                ("depth", "Буын", "қадам"), ("is_seed", "Бастапқы клиент", ""),
            ):
                node_fact(client, key, label, unit)
        if task == "seed_paths":
            title = f"Seed-клиенттерден {alias(client)} клиентіне дейінгі жолдар"
            node_fact(client, "reachable_seed_count", "Бағытталған жолмен жететін өзге seed", "клиент")
            paths = observed_seed_paths(analysis, client, limit=5)
            add("Өзге seed-тен ең аз қадам", min((len(path) - 1 for path in paths), default=None), "қадам", "graph.min_other_seed_hops")
            add("Көрсетілген seed жолдары", len(paths), "жол", "graph.seed_paths_shown")
            for index, path in enumerate(paths, 1):
                # Bound each path's payload while preserving the true hop count.
                visible = path if len(path) <= 12 else path[:6] + [None] + path[-6:]
                display = " → ".join(alias(node) if node is not None else "…" for node in visible)
                add(f"Seed жолы {index}", display, "", "graph.seed_path")
                add(f"Seed жолы {index} · қадам саны", len(path) - 1, "қадам", "graph.seed_path_hops")
                add(f"Seed жолы {index} · ортасы қысқартылған", len(path) > 12, "", "graph.seed_path_truncated")
            warnings.append("Әр жететін seed үшін бір ең қысқа құрылымдық жол, ең көбі бес seed көрсетіледі. Он екі клиенттен ұзын жолдың ортасы қысқартылады. Бұл барлық жолдар немесе дәл сол ақшаның уақытпен қозғалысы емес; клиенттің өзі бастапқы seed ретінде саналмайды.")
        elif task == "client_flows":
            title = f"{alias(client)} клиентінің бақыланған ақша бағыттары"
            add("Сұралған бағыт", {"both": "Кіріс және шығыс", "incoming": "Кіріс", "outgoing": "Шығыс"}[direction], "", "request.direction")
            for incoming in (True, False):
                if (incoming and direction == "outgoing") or (not incoming and direction == "incoming"):
                    continue
                neighbors = (analysis.graph.predecessors(client) if incoming else analysis.graph.successors(client))
                neighbors = [other for other in neighbors if other != client]

                def edge(other):
                    return analysis.graph.edges[other, client] if incoming else analysis.graph.edges[client, other]

                ordered = sorted(neighbors, key=lambda other: (-float(edge(other)["sum_kzt"]), other))
                prefix = "Кіріс" if incoming else "Шығыс"
                add(f"{prefix} · өзге клиенттер саны", len(ordered), "клиент", "graph.flow_counterparties")
                add(f"{prefix} · көрсетілген клиенттер", min(len(ordered), 5), "клиент", "graph.flow_shown")
                for other in ordered[:5]:
                    source, target = (other, client) if incoming else (client, other)
                    label = f"{alias(source)} → {alias(target)}"
                    add(f"{label} · бақыланған сома", float(edge(other)["sum_kzt"]), "₸", "graph.flow_edge_sum_kzt")
                    add(f"{label} · операциялар", int(edge(other)["n_tx"]), "операция", "graph.flow_edge_n_tx")
            self_edge = analysis.graph.get_edge_data(client, client)
            add("Өзіне аударымдардың сомасы", float(self_edge["sum_kzt"]) if self_edge else 0.0, "₸", "graph.self_transfer_sum_kzt")
            warnings.append("Әр сұралған бағытта жиынтық сомасы ең үлкен бес өзге клиент қана көрсетіледі. Клиенттің толық кіріс/шығыс сомалары барлық бақыланған байланыстар мен өзіне аударымдарды қамтиды. Сомалар шот қалдығы емес.")
        else:
            title = f"{alias(client)} клиентінің дерек толықтығы" if client is not None else "Бақыланған желінің дерек толықтығы"
            selected = [rows[client]] if client is not None else list(rows.values())
            add("Тексерілген клиенттер", len(selected), "клиент", "observation.selected_nodes")
            for key, label in (("is_seed", "Кірісі толық емес seed"), ("truncated_by_depth", "Шекарадағы клиенттер"), ("is_isolated", "Байланысы көрінбейтін клиенттер")):
                add(label, sum(bool(row[key]) for row in selected), "клиент", "observation." + key)
            requests = ["Бақылау мерзімі мен іріктеу ережесін растау; қажет болса кеңірек мерзімдегі, басқа банктердегі және кейстегі 5 000 ₸ шегінен төмен операцияларды сұрату."]
            if any(row["is_seed"] for row in selected):
                requests.append("Seed-клиенттердің толық кіріс операциялары мен қаражат көздерін сұрату.")
            if any(row["truncated_by_depth"] for row in selected):
                requests.append("Төртінші буыннан кейінгі шығыс операциялары мен келесі алушыларды сұрату.")
            if any(row["is_isolated"] for row in selected):
                requests.append("Байланысы көрінбейтін клиенттердің идентификатор сәйкестігін және толық операциялар үзіндісін тексеру.")
            if any(int(row["temporal_eligible_in_tx"]) == 0 for row in selected):
                requests.append("Кірістен кейін кемінде екі толық күнді қамтитын бақылауды кеңейту; уақыттық дәлел жеткіліксіз клиенттер бар.")
            for index, request in enumerate(requests, 1):
                add(f"Қосымша дерек сұрауы {index}", request, "", "observation.next_request")
            warnings.append("Жоқ операциялар ойдан толықтырылмайды. Толық баланс, клиенттің қызметі, төлем мақсаты және расталған рөлдер бұл графта берілмеген. Сұраулар дерек толықтығын тексеруге арналған.")
    elif task == "top_priority":
        if any(value is not None for value in (gid, cluster_id, gids)):
            raise ValueError("Тексеру кезегіне жеке gid немесе кластер берілмейді")
        selected = ranked(rows)[:int(top_n)]
        title = f"Алдымен тексерілетін {len(selected)} клиент"
        add("Сұралған кезек көлемі", int(top_n), "клиент", "request.top_n")
        add("Көрсетілген кезек көлемі", len(selected), "клиент", "roles.priority_order")
        add("Кезек үзіндісіне кірмеген клиенттер", len(rows) - len(selected), "клиент", "roles.priority_order")
        for rank, client in enumerate(selected, 1):
            compact_client(client, rank)
    elif task == "cluster_summary":
        if gid is not None or gids is not None:
            raise ValueError("Кластер тапсырмасына тек cluster_id беріледі")
        try:
            cluster = _exact_integer(cluster_id)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("Кластер нөмірі бүтін сан болуы керек") from exc
        members = [client for client, row in rows.items() if int(row["cluster_id"]) == cluster]
        if not members:
            raise ValueError("Көрсетілген кластер табылмады")
        member_set = set(members)
        internal = [(src, dst, data) for src, dst, data in analysis.graph.edges(data=True) if src in member_set and dst in member_set]
        title = f"{cluster}-кластердің құрылымдық қорытындысы"
        add("Кластер нөмірі", cluster, "", "roles.cluster_id")
        add("Кластердегі клиенттер", len(members), "клиент", "roles.cluster_id")
        add("Кластердегі seed", sum(bool(rows[client]["is_seed"]) for client in members), "клиент", "graph.is_seed")
        add("Кластердегі 4-буын", sum(rows[client]["depth"] == 4 for client in members), "клиент", "graph.depth")
        add("Кластер ішіндегі бағытталған байланыстар", len(internal), "байланыс", "graph.internal_edges")
        add("Кластер ішіндегі айналым", math.fsum(float(data["sum_kzt"]) for _, _, data in internal), "₸", "graph.internal_sum_kzt")
        for role, label in ROLE_LABELS.items():
            add(f"Кластердегі рөл: {label}", sum(rows[client]["role"] == role for client in members), "клиент", "roles.role")
        selected = ranked(members)[:5]
        add("Көрсетілген басым мүшелер", len(selected), "клиент", "roles.priority_order")
        add("Мүшелер үзіндісіне кірмегендер", len(members) - len(selected), "клиент", "roles.priority_order")
        for rank, client in enumerate(selected, 1):
            compact_client(client, rank)
        warnings.append("Кластер — байланысы тығыз құрылымдық топ; ұйымға немесе қылмыстық топқа мүшелікті дәлелдемейді.")
    else:
        if gid is not None or cluster_id is not None:
            raise ValueError("Ортақ алушылар тапсырмасына тек gids тізімі беріледі")
        if not isinstance(gids, (list, tuple)) or not 2 <= len(gids) <= 5:
            raise ValueError("Екіден беске дейін әртүрлі gid енгізіңіз")
        senders = [_gid(value, rows) for value in gids]
        if len(set(senders)) != len(senders):
            raise ValueError("Кіріс gid мәндері қайталанбауы керек")
        senders.sort()
        for index, client in enumerate(senders, 1):
            add(f"Таңдалған жіберуші {index}", alias(client), "", "request.senders")
        shared = set.intersection(*(set(analysis.graph.successors(client)) for client in senders)) - set(senders)
        amounts = {recipient: math.fsum(float(analysis.graph.edges[client, recipient]["sum_kzt"]) for client in senders) for recipient in shared}
        selected = sorted(shared, key=lambda recipient: (-amounts[recipient], recipient))[:10]
        title = "Таңдалған клиенттердің ортақ тікелей алушылары"
        add("Ортақ алушылардың толық саны", len(shared), "клиент", "graph.successor_intersection")
        add("Көрсетілген ортақ алушылар", len(selected), "клиент", "graph.successor_intersection")
        add("Үзіндіге кірмеген ортақ алушылар", len(shared) - len(selected), "клиент", "graph.successor_intersection")
        for recipient in selected:
            name = alias(recipient)
            add(f"{name} · Таңдалған жіберушілерден кіріс", amounts[recipient], "₸", "graph.selected_sender_sum_kzt")
            add(f"{name} · Таңдалған жіберушілерден операциялар", sum(int(analysis.graph.edges[client, recipient]["n_tx"]) for client in senders), "операция", "graph.selected_sender_n_tx")
            for key, label, unit in (
                ("role", "Рөл болжамы", ""), ("priority_score", "Тексеру басымдығы", "ұпай"),
                ("in_kzt", "Барлық бақыланған кіріс", "₸"), ("out_kzt", "Барлық бақыланған шығыс", "₸"),
                ("depth", "Буын", "қадам"), ("is_seed", "Бастапқы клиент", ""),
            ):
                node_fact(recipient, key, label, unit)
        warnings.append("Ортақ алушыға таңдалған әр жіберушіден тікелей байланыс болуы керек; жіберушілердің өздері алушылар тізімінен шығарылған. Ең көбі 10 алушы таңдалған жіберушілерден түскен жиынтық сома бойынша көрсетіледі.")

    if len(facts) > 100:
        raise ValueError("Дәлелдер саны 100-ден аспауы керек")
    bundle = EvidenceBundle(task, title, facts, warnings, aliases)
    json.dumps(bundle.public_payload(), ensure_ascii=False, allow_nan=False)
    return bundle


def local_report(bundle: EvidenceBundle) -> str:
    """Readable deterministic report; alias resolution stays on this computer."""
    lines = ["Жергілікті есеп · AI қолданылған жоқ", "", bundle.title, ""]
    if bundle.aliases:
        lines += ["Клиенттердің жергілікті сәйкестігі:"]
        lines += [f"- {name} → gid {gid}" for name, gid in bundle.aliases.items()]
        lines += [""]
    for fact in bundle.facts:
        value = fact["value"]
        if value is None:
            display = "дерек жеткіліксіз"
        elif isinstance(value, bool):
            display = "иә" if value else "жоқ"
        elif isinstance(value, float):
            # Preserve round-trip precision instead of rounding a large KZT
            # amount to ten significant digits and silently losing its cents.
            display = str(int(value)) if value.is_integer() else repr(value)
        else:
            display = str(value)
        suffix = f" {fact['unit']}" if fact["unit"] else ""
        lines.append(f"[{fact['id']}] {fact['label']}: {display}{suffix}.")
    lines += ["", "Талдаудың шектеулері:"]
    lines += [f"- {warning}" for warning in bundle.warnings]
    return "\n".join(lines)
