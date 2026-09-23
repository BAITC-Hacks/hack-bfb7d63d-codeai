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
from moneymap.graph import AnalysisResult
from moneymap.roles import ROLE_LABELS, RoleAnalysis


TASKS = {"explain_client", "report_client", "top_priority", "cluster_summary", "common_recipients"}
BASE_WARNINGS = [
    "Көрсеткіштер толық бақыланған жиыннан жергілікті есептелген; карта сүзгілері оларды өзгертпейді.",
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
    ("in_deg", "Бірегей жіберушілер", "клиент"),
    ("out_deg", "Бірегей алушылар", "клиент"),
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
    ("first_in_date", "Алғашқы кіріс күні", ""),
    ("last_in_date", "Соңғы кіріс күні", ""),
    ("first_out_date", "Алғашқы шығыс күні", ""),
    ("last_out_date", "Соңғы шығыс күні", ""),
    ("temporal_contradiction", "Барлық шығыс алғашқы кірістен бұрын болған", ""),
    ("temporal_order_status", "Күндер бойынша бақылау мәртебесі", ""),
    ("transit_excluded_by_time", "Қатынас сай, бірақ уақыт бойынша transit алынып тасталған", ""),
    ("priority_consolidation", "Басымдық үлесі: жинақталу", "ұпай"),
    ("priority_in_kzt", "Басымдық үлесі: кіріс сомасы", "ұпай"),
    ("priority_in_deg", "Басымдық үлесі: жіберушілер", "ұпай"),
    ("priority_betweenness", "Басымдық үлесі: аралық орталықтық", "ұпай"),
    ("priority_seed_reach", "Басымдық үлесі: seed-тен жету", "ұпай"),
    ("priority_out_deg", "Басымдық үлесі: алушылар", "ұпай"),
    ("priority_pagerank", "Басымдық үлесі: PageRank", "ұпай"),
)

PRIORITY_LABELS = {
    "consolidation": "жинақталу", "in_kzt": "кіріс сомасы", "in_deg": "жіберушілер",
    "betweenness": "аралық орталықтық", "seed_reach": "seed-тен жету",
    "out_deg": "алушылар", "pagerank": "PageRank",
}


def _executed_rule(row, roles) -> str:
    """Describe the actual configured gate using trusted code and computed values."""
    rules = roles.config["rules"]
    if row["is_isolated"]:
        return "Бақыланған байланыс жоқ → peripheral; басқа рөлге дерек жеткіліксіз."
    if row.get("self_loop_only", False):
        return "Тек өзіне аударым бар → peripheral; сыртқы байланыс белгісі жоқ."
    if row["depth"] == 4:
        return "depth=4 → peripheral; әрі қарайғы шығыс бақыланбаған."
    role = row["role"]
    observed = f"depth={row['depth']} < 4; оқшау емес; "
    if role == "coordinator":
        cutoff = roles.summary["thresholds"]["coordinator_betweenness_cutoff"]
        return observed + (
            f"жіберуші {row['in_deg']} ≥ {rules['coordinator_min_in_deg']}; "
            f"алушы {row['out_deg']} ≥ {rules['coordinator_min_out_deg']}; "
            f"seed-тен жету {row['reachable_seed_count']} ≥ {rules['coordinator_min_seed_reach']}; "
            f"betweenness={row['betweenness']} > 0 және ≥ {cutoff} "
            f"(оң мәндер квантилі {rules['coordinator_betweenness_quantile']})."
        )
    if role == "distributor":
        return observed + f"алушы {row['out_deg']} ≥ {rules['distributor_min_out_deg']}."
    ratio = row["observed_flow_ratio"]
    if role == "consolidator":
        return observed + (
            f"қатынас жарамды; жіберуші {row['in_deg']} ≥ {rules['consolidator_min_in_deg']}; "
            f"шығыс/кіріс {ratio} ≤ {rules['consolidator_max_ratio']}."
        )
    if role == "transit":
        return observed + (
            f"қатынас жарамды; жіберуші {row['in_deg']} ≥ 1; алушы {row['out_deg']} ≥ 1; "
            f"{rules['transit_min_ratio']} ≤ шығыс/кіріс {ratio} ≤ {rules['transit_max_ratio']}; "
            "барлық шығыс алғашқы кірістен бұрын болғаны байқалмаған."
        )
    if role == "terminal":
        return observed + f"қатынас жарамды; кіріс {row['in_kzt']} > 0; шығыс көрші {row['out_deg']} = 0."
    reason = "Seed кірісі толық емес: қатынасқа негізделген ережелер қолданылмайды. " if row["is_seed"] else ""
    if row.get("temporal_contradiction", False):
        reason += "Барлық шығыс алғашқы кірістен бұрын: transit ережесі қабылданбайды. "
    return observed + reason + "Алдыңғы рөл ережелері орындалмаған → peripheral."


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
        source = "roles." + key if key in ("role", "role_score", "cluster_id", "priority_score", "transit_excluded_by_time") or key.startswith("priority_") else "graph." + key
        value = ROLE_LABELS[rows[client]["role"]] if key == "role" else rows[client][key]
        add(f"{alias(client)} · {label}", value, unit, source)

    def rule_fact(client):
        add(f"{alias(client)} · Орындалған рөл ережесі", _executed_rule(rows[client], roles), "", "roles.executed_rule")

    def priority_fact(client):
        # A scalar fact retains every actual contribution while top-10 stays
        # within the 100-fact contract. These are values, not model deductions.
        parts = [f"{label}={rows[client]['priority_' + key]} (салмақ {roles.config['priority']['weights'][key]})"
                 for key, label in PRIORITY_LABELS.items()]
        add(f"{alias(client)} · Басымдықтың жеті үлесі", "; ".join(parts), "", "roles.contribution_breakdown")

    def ranked(members):
        return sorted(members, key=lambda client: (-float(rows[client]["priority_score"]), -float(rows[client]["in_kzt"]), client))

    def compact_client(client, rank):
        add(f"{alias(client)} · Тексеру кезегі", rank, "орын", "roles.priority_order")
        for key, label, unit in (
            ("role", "Рөл болжамы", ""), ("priority_score", "Тексеру басымдығы", "ұпай"),
            ("in_kzt", "Кіріс сомасы", "₸"), ("in_deg", "Бірегей жіберушілер", "клиент"),
            ("depth", "Буын", "қадам"), ("is_seed", "Бастапқы клиент", ""),
        ):
            node_fact(client, key, label, unit)
        rule_fact(client)
        priority_fact(client)

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
            if key in rows[client]:
                node_fact(client, key, label, unit)
        rule_fact(client)
        warnings.append("Уақыттық үлеске соңғы екі күннің кірістері кірмейді; сол күнгі аударым реті анықталмайды. Орташа күн тек кейінгі шығысы байқалған кірістерге шартты есептеледі.")
        if rows[client]["is_isolated"]:
            warnings.append(f"{alias(client)}: бақыланған аударым жоқ; бұл қауіпсіздік туралы қорытынды емес.")
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
    if bundle.task == "report_client":
        return analyst_note(bundle)
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


def _fact_line(fact: dict) -> str:
    value = fact["value"]
    if value is None:
        display = "дерек жеткіліксіз"
    elif isinstance(value, bool):
        display = "иә" if value else "жоқ"
    elif isinstance(value, float):
        display = str(int(value)) if value.is_integer() else repr(value)
    else:
        display = str(value)
    unit = f" {fact['unit']}" if fact["unit"] else ""
    return f"[{fact['id']}] {fact['label']}: {display}{unit}."


def analyst_note(bundle: EvidenceBundle) -> str:
    """Concise, reproducible analyst note and specific next data request.

    The content is selected from the same evidence bundle as the detailed view.
    No free-form model text is needed for the analyst's primary report.
    """
    facts = {fact["source"]: fact for fact in bundle.facts}

    def value(source):
        return facts.get(source, {}).get("value")

    lines = ["Жергілікті есеп · AI қолданылған жоқ", "", "Талдаушыға қысқа анықтама"]
    lines.extend(f"{alias} → gid {gid}" for alias, gid in bundle.aliases.items())
    start, end = value("dataset.min_date"), value("dataset.max_date")
    lines += [f"Бақылау кезеңі: {start or 'анықталмаған'} — {end or 'анықталмаған'}.", "", "Бақыланған жағдай:"]
    for source in ("roles.role", "roles.priority_score", "graph.in_kzt", "graph.out_kzt", "graph.in_deg", "graph.out_deg"):
        if source in facts:
            lines.append(_fact_line(facts[source]))
    lines += ["", "Рөлдің нақты негізі:"]
    if "roles.executed_rule" in facts:
        lines.append(_fact_line(facts["roles.executed_rule"]))
    contributions = [fact for fact in bundle.facts if fact["source"] in {"roles.priority_" + key for key in PRIORITY_LABELS}]
    strongest = sorted(contributions, key=lambda fact: -float(fact["value"]))[:3]
    lines += ["", "Басымдыққа ең көп әсер еткен белгілер:"]
    lines.extend(_fact_line(fact) for fact in strongest if fact["value"] > 0)
    if not any(fact["value"] > 0 for fact in strongest):
        lines.append("Бақыланған салмақталған белгілер нөлге тең; бұл қауіпсіздік қорытындысы емес.")
    if value("graph.is_isolated"):
        action = "Осы gid үшін кезеңдегі операциялар қамтылуын және seed тізіміне енгізу негізін тексеріңіз; байланыссыз жазбаны өшірмеңіз."
    elif value("graph.truncated_by_depth"):
        action = "Осы клиенттен әрі қарайғы шығыс операцияларын келесі буынға дейін сұратыңыз; қазіргі үзіндімен соңғы алушы деп шешпеңіз."
    elif value("graph.temporal_contradiction"):
        action = "Алғашқы кіріс пен соңғы шығыс күндерін операциялармен салыстырыңыз; ертерек кезеңдегі кірістерді сұратыңыз. Бұл айдың кірісі ертерек шығысқа себеп болған деп есептемеңіз."
    elif value("graph.is_seed"):
        action = "Seed клиентінің осы және алдыңғы кезеңдегі толық кіріс операцияларын сұратыңыз; көрінетін шығыс/кірісті шот балансы ретінде қолданбаңыз."
    elif value("graph.out_deg") == 0:
        action = "Осы кезеңнен кейінгі және үзіндіге кірмеген шығыс операцияларын сұратыңыз; шығыс байқалмағаны қаражат толық сақталды дегенді білдірмейді."
    else:
        action = "Картадағы тікелей кіріс/шығыс байланыстарын ашып, бастапқы операциялардың күндері мен сомаларын салыстырыңыз; нақты реттілік керек болса сағат/минут дерегін сұратыңыз."
    lines += ["", "Талдаушының келесі қадамы:", action, "", "Шектеу: рөл мен басымдық — тексеру гипотезасы. Бір банк пен бір кезеңнің үзіндісі толық қаржылық көріністі бермейді; байланыс дәл сол қаражаттың қозғалысын дәлелдемейді."]
    return "\n".join(lines)
