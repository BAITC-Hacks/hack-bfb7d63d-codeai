"""Supported questions must resolve to exact local facts without network use."""

import json
import socket

import pandas as pd
import pytest

from moneymap.ai_facts import build_evidence, local_report
from moneymap.demo import create_demo_frames
from moneymap.graph import analyze_dataset
from moneymap.graph_questions import answer_question, GraphQuestionError, parse_question
from moneymap.roles import classify_graph


BASE = 234_567_890_123_456_700


@pytest.fixture
def network():
    frames = create_demo_frames()
    for name, columns in (("nodes", ["gid"]), ("edges", ["src", "dst"]), ("transactions", ["src", "dst"])):
        for column in columns:
            frames[name][column] += BASE
    analysis = analyze_dataset(frames)
    return analysis, classify_graph(analysis)


@pytest.mark.parametrize("question,task,arguments", [
    (f"Неге gid {BASE + 1005} маңызды?", "explain_client", {"gid": str(BASE + 1005)}),
    (f"Объясни роль клиента {BASE + 1005}", "explain_client", {"gid": str(BASE + 1005)}),
    ("Алдымен тексеретін топ 3 клиент", "top_priority", {"top_n": 3}),
    ("Покажи топ-10", "top_priority", {"top_n": 10}),
    ("Кімді алдымен тексеру керек?", "top_priority", {"top_n": 5}),
    ("Объясни кластер 1", "cluster_summary", {"cluster_id": 1}),
    (f"{BASE + 1001} және {BASE + 1002} ортақ алушыларын көрсет", "common_recipients", {"gids": [str(BASE + 1001), str(BASE + 1002)]}),
    (f"Общие получатели {BASE + 1001}, {BASE + 1002}", "common_recipients", {"gids": [str(BASE + 1001), str(BASE + 1002)]}),
    (f"Seed-тен gid {BASE + 1008}-ке жол", "seed_paths", {"gid": str(BASE + 1008)}),
    (f"Пути от seed к {BASE + 1008}", "seed_paths", {"gid": str(BASE + 1008)}),
    (f"Каких данных не хватает для gid {BASE + 1014}?", "data_completeness", {"gid": str(BASE + 1014)}),
    ("Қандай деректер жетіспейді?", "data_completeness", {}),
    (f"Кімге gid {BASE + 1008} ақша жіберді?", "client_flows", {"gid": str(BASE + 1008), "direction": "outgoing"}),
    (f"Входящие переводы {BASE + 1005}", "client_flows", {"gid": str(BASE + 1005), "direction": "incoming"}),
    (f"Кіріс және шығыс {BASE + 1005}", "client_flows", {"gid": str(BASE + 1005), "direction": "both"}),
])
def test_kazakh_and_russian_questions_resolve_one_exact_task(network, question, task, arguments):
    analysis, roles = network
    parsed = parse_question(question, available_gids=analysis.graph, cluster_ids=roles.clusters.cluster_id)
    assert parsed.task == task
    assert parsed.arguments == arguments


@pytest.mark.parametrize("question", [
    "", "а" * 601, "Ауа райы қандай?", "Желі ертең қалай өзгереді?",
    "Топ 1000", "Топ -3", "Топ 2 және 3", "топ 5 кіріс сомасы бойынша",
    "Топ 5 және кластер 1", "Объясни кластер 999999", "Неге gid 9999 маңызды?",
    "Неге gid 1e18 маңызды?", "Неге gid 9223372036854775808 маңызды?",
    f"Неге gid {BASE + 1005}.0 маңызды?",
    f"{BASE + 1001} және {BASE + 1001} ортақ алушылар",
    "1 2 3 4 5 6 ортақ алушылар",
    f"{BASE + 1001} мен {BASE + 1005} арасындағы жол",
    f"Шығыс {BASE + 1005} 2026-07-03", f"Шығыс {BASE + 1005} соңғы 5 күн",
    f"Шығыс {BASE + 1005} > 5000", "import os; exec(1)",
    f"Входящие {BASE + 1005} в июне", f"Кіріс {BASE + 1005} өткен аптада",
    f"Общие получатели {BASE + 1001} {BASE + 1002} кроме {BASE + 1003}",
    "Топ 5 тек seed емес клиенттер", "Топ 5 только транзитные счета", "Топ 5 seed", "Топ 5 транзитных клиентов",
    f"Кімге gid {BASE + 1005} ақша жібермеді?", f"Кому gid {BASE + 1005} не отправлял деньги?",
    "Каких данных не хватает для gid9999?", "Қандай дерек жетіспейді gid1005?", "Каких данных не хватает для клиента?",
    f"Неге {BASE + 1005} маңызды? api_key=sk-secret", f"Клиент {BASE + 1005} кінәлі ме?",
])
def test_unsupported_ambiguous_unknown_and_unbounded_questions_are_rejected(network, question):
    analysis, roles = network
    with pytest.raises(GraphQuestionError):
        answer_question(analysis, roles, question)


def test_answers_are_local_and_payloads_contain_neither_question_nor_private_ids(network, monkeypatch):
    analysis, roles = network

    def no_network(*args, **kwargs):
        raise AssertionError("Question attempted network access")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr("moneymap.ai_provider.requests.post", no_network)
    question = f"Неге gid {BASE + 1005} маңызды?"
    bundle = answer_question(analysis, roles, question)
    assert bundle.facts == build_evidence(analysis, roles, "explain_client", gid=str(BASE + 1005)).facts
    assert str(BASE + 1005) in local_report(bundle)
    for query in (question, f"Seed-тен {BASE + 1008}-ке жол", f"Кіріс және шығыс {BASE + 1005}", "Қандай дерек жетіспейді?"):
        bundle = answer_question(analysis, roles, query)
        public = json.dumps(bundle.public_payload(), ensure_ascii=False, allow_nan=False)
        assert query not in public
        assert all(str(gid) not in public for gid in analysis.graph)
        assert len(bundle.facts) <= 100


def test_small_ids_do_not_change_rank_count_into_client_identity():
    parsed = parse_question("Приоритетные 3 клиента", available_gids=[1, 2, 3], cluster_ids=[1])
    assert parsed.task == "top_priority" and parsed.arguments == {"top_n": 3}
    parsed = parse_question("Неге gid 3 басым?", available_gids=[1, 2, 3], cluster_ids=[1])
    assert parsed.task == "explain_client" and parsed.arguments == {"gid": "3"}


def test_seed_path_facts_preserve_direction_and_actual_hops_and_isolation(network):
    analysis, roles = network
    bundle = answer_question(analysis, roles, f"Seed-тен {BASE + 1008}-ке жол")
    paths = [fact["value"] for fact in bundle.facts if fact["source"] == "graph.seed_path"]
    actual = [[int(bundle.aliases[alias]) for alias in path.split(" → ")] for path in paths]
    assert actual == [[BASE + seed, BASE + 1005, BASE + 1008] for seed in (1001, 1002, 1003)]
    assert [fact["value"] for fact in bundle.facts if fact["source"] == "graph.seed_path_hops"] == [2, 2, 2]
    isolated = answer_question(analysis, roles, f"Seed-тен {BASE + 1004}-ке жол")
    assert [fact["value"] for fact in isolated.facts if fact["source"] == "graph.seed_paths_shown"] == [0]


def test_completeness_answers_request_evidence_without_filling_missing_transactions(network):
    analysis, roles = network
    boundary = answer_question(analysis, roles, f"Каких данных не хватает для {BASE + 1014}?")
    requests = [fact["value"] for fact in boundary.facts if fact["source"] == "observation.next_request"]
    assert any("Төртінші" in request for request in requests)
    assert not any("Seed-клиенттердің" in request for request in requests)
    seed = answer_question(analysis, roles, f"Қандай дерек жетіспейді {BASE + 1004}?")
    requests = [fact["value"] for fact in seed.facts if fact["source"] == "observation.next_request"]
    assert any("Seed-клиенттердің" in request for request in requests)
    assert any("идентификатор" in request for request in requests)


def test_flow_answers_use_actual_directed_edge_amounts_not_total_turnover(network):
    analysis, roles = network
    bundle = answer_question(analysis, roles, f"Кіріс {BASE + 1005}")
    amounts = [fact["value"] for fact in bundle.facts if fact["source"] == "graph.flow_edge_sum_kzt"]
    assert amounts == [80000, 75000, 65000]
    assert sum(amounts) == 220000
    counts = [fact["value"] for fact in bundle.facts if fact["source"] == "graph.flow_edge_n_tx"]
    assert counts == [1, 2, 1]
    for fact in bundle.facts:
        if fact["source"] == "graph.flow_edge_sum_kzt":
            assert "→ C001" in fact["label"]
    assert len(analysis.graph) == 16


def test_long_paths_have_explicit_truncation_and_retain_true_hop_count():
    nodes = pd.DataFrame({"gid": range(BASE, BASE + 16), "depth": [0] + [1] * 15, "is_seed": [True] + [False] * 15})
    tx = pd.DataFrame({"src": range(BASE, BASE + 15), "dst": range(BASE + 1, BASE + 16), "date": pd.to_datetime(["2026-07-01"] * 15), "sum_kzt": [5000] * 15})
    edges = tx[["src", "dst", "sum_kzt"]].assign(n_tx=1, depth=1)
    analysis = analyze_dataset({"nodes": nodes, "edges": edges, "transactions": tx})
    bundle = answer_question(analysis, classify_graph(analysis), f"Seed-тен {BASE + 15}-ке жол")
    values = {fact["source"]: fact["value"] for fact in bundle.facts}
    assert values["graph.seed_path_hops"] == 15
    assert values["graph.seed_path_truncated"] is True
    assert "…" in values["graph.seed_path"]
    assert len(bundle.aliases) == 12


def test_seed_path_minimum_excludes_self_seed_zero_hop():
    nodes = pd.DataFrame({"gid": [1, 2], "depth": [0, 0], "is_seed": [True, True]})
    tx = pd.DataFrame({"src": [1], "dst": [2], "date": pd.to_datetime(["2026-07-01"]), "sum_kzt": [5000]})
    edges = tx[["src", "dst", "sum_kzt"]].assign(n_tx=1, depth=1)
    analysis = analyze_dataset({"nodes": nodes, "edges": edges, "transactions": tx})
    roles = classify_graph(analysis)
    bundle = answer_question(analysis, roles, "Seed-тен gid 2-ге жол")
    values = {fact["source"]: fact["value"] for fact in bundle.facts}
    assert values["graph.min_other_seed_hops"] == values["graph.seed_path_hops"] == 1
    empty = answer_question(analysis, roles, "Seed-тен gid 1-ге жол")
    assert next(fact["value"] for fact in empty.facts if fact["source"] == "graph.min_other_seed_hops") is None
