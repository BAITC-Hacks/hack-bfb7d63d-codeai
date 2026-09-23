"""Dataset-scoped analyst assertions and evaluation against supplied labels.

These pure functions never fetch referenced documents, infer customer identity,
change model predictions, train a model, or write files. The HTTP application
owns persistence. An analyst-supported assertion is not judicial ground truth.
"""

from __future__ import annotations

from copy import deepcopy
import csv
import hashlib
from io import StringIO
import json
import re
from typing import Any

ROLES = ("consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral")
STATUSES = ("unreviewed", "in_review", "supported", "rejected")
EVIDENCE_KINDS = ("ownership", "control", "transaction", "other")
LABEL_FIELDS = ("gid", "verified_role", "source_reference", "reviewer")
NOTICE = ("Analyst-supplied assertions and labels are not independently verified or judicial findings. "
          "Evaluation describes agreement on the supplied subset, not proven real-world accuracy.")


def _gid(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("gid must be an exact int64 integer or decimal string")
    if isinstance(value, str) and not re.fullmatch(r"-?\d{1,20}", value.strip()):
        raise ValueError("gid must be an exact int64 integer or decimal string")
    integer = int(value)
    if not -(2**63) <= integer < 2**63:
        raise ValueError("gid is outside the int64 range")
    return str(integer)


def _nodes(analysis: dict) -> dict[str, dict]:
    if not isinstance(analysis, dict) or not isinstance(analysis.get("nodes"), list):
        raise ValueError("analysis must contain a nodes list")
    result = {}
    for node in analysis["nodes"]:
        if not isinstance(node, dict) or "gid" not in node:
            raise ValueError("analysis.nodes contains an invalid record")
        key = _gid(node["gid"])
        if key in result:
            raise ValueError(f"analysis contains duplicate gid {key}")
        if node.get("role") not in ROLES:
            raise ValueError(f"analysis node {key} has an unsupported predicted role")
        result[key] = node
    return result


def _known_gid(value: Any, nodes: dict[str, dict]) -> str:
    key = _gid(value)
    if key not in nodes:
        raise ValueError(f"Unknown gid: {key}")
    return key


def _text(value: Any, field: str, *, maximum: int, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise ValueError(f"{field} must contain {'1' if required else '0'} to {maximum} characters")
    if any(ord(char) < 32 and char not in "\n\t\r" for char in value):
        raise ValueError(f"{field} contains unsupported control characters")
    return value


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Data must be finite, JSON-safe values; NaN and Infinity are not allowed") from exc


def dataset_fingerprint(analysis: dict) -> str:
    """Return a stable data fingerprint, excluding runtime and predictions.

    Prefer a producer-supplied SHA-256 of normalized source records when
    ``meta.dataset_fingerprint`` exists. Otherwise hash the observable graph,
    per-node temporal observations and daily totals. The fallback identifies
    that observed representation, not unavailable raw transaction rows.
    """
    nodes = _nodes(analysis)
    meta = analysis.get("meta") or {}
    supplied = meta.get("dataset_fingerprint")
    if supplied is not None:
        if not isinstance(supplied, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", supplied):
            raise ValueError("meta.dataset_fingerprint must be a 64-character SHA-256 hex digest")
        return supplied.lower()
    observations = []
    for key in sorted(nodes, key=int):
        node = nodes[key]
        observations.append({"gid": key, "depth": node.get("depth"), "is_seed": node.get("is_seed"),
                             "temporal": {field: (node.get("temporal") or {}).get(field) for field in
                                          ("active_days", "incoming_active_days", "outgoing_active_days",
                                           "synchronized_payers", "first_observed", "last_observed", "last_incoming")}})
    edges = [{"src": _known_gid(edge["src"], nodes), "dst": _known_gid(edge["dst"], nodes),
              "sum_kzt": float(edge["sum_kzt"]), "n_tx": edge.get("n_tx"), "depth": edge.get("depth")}
             for edge in analysis.get("edges", [])]
    edges.sort(key=lambda edge: (int(edge["src"]), int(edge["dst"]), _json(edge)))
    timeline = [{"date": str(day["date"]), "sum_kzt": float(day["sum_kzt"]), "n_tx": day.get("n_tx")}
                for day in analysis.get("timeline", [])]
    timeline.sort(key=lambda day: (day["date"], _json(day)))
    data = {"fingerprint_version": 1, "nodes": observations, "edges": edges, "timeline": timeline,
            "period_start": meta.get("period_start"), "period_end": meta.get("period_end")}
    return hashlib.sha256(_json(data).encode("utf-8")).hexdigest()


def _labels(analysis: dict, labels: Any) -> list[dict]:
    nodes = _nodes(analysis)
    if not isinstance(labels, list):
        raise ValueError("labels must be a list of label records")
    _json(labels)
    seen = set()
    result = []
    for index, label in enumerate(labels):
        if not isinstance(label, dict) or set(label) != set(LABEL_FIELDS):
            raise ValueError(f"labels[{index}] must contain exactly {', '.join(LABEL_FIELDS)}")
        key = _known_gid(label["gid"], nodes)
        if key in seen:
            raise ValueError(f"Duplicate label gid: {key}")
        seen.add(key)
        if label["verified_role"] not in ROLES:
            raise ValueError(f"Label {key}: verified_role must be one of the six supported roles")
        result.append({"gid": key, "verified_role": label["verified_role"],
                       "source_reference": _text(label["source_reference"], "source_reference", maximum=1000, required=True),
                       "reviewer": _text(label["reviewer"], "reviewer", maximum=120, required=True)})
    return sorted(result, key=lambda label: int(label["gid"]))


def evaluate_labels(analysis: dict, labels: list[dict]) -> dict:
    """Compare frozen current role predictions with explicit analyst labels.

    Undefined precision/recall/F1 is null, not a manufactured zero. Macro F1
    averages only classes with supplied label support. No label is synthesized
    from the predictions, and no training or threshold adjustment occurs.
    """
    nodes = _nodes(analysis)
    validated = _labels(analysis, labels)
    confusion = {actual: {predicted: 0 for predicted in ROLES} for actual in ROLES}
    for label in validated:
        confusion[label["verified_role"]][nodes[label["gid"]]["role"]] += 1
    per_class = {}
    for role in ROLES:
        true_positive = confusion[role][role]
        support = sum(confusion[role].values())
        predicted_count = sum(confusion[actual][role] for actual in ROLES)
        denominator = support + predicted_count
        per_class[role] = {"precision": true_positive / predicted_count if predicted_count else None,
                           "recall": true_positive / support if support else None,
                           "f1": 2 * true_positive / denominator if denominator else None,
                           "support": support, "predicted_count": predicted_count,
                           "true_positive": true_positive}
    count = len(validated)
    supported = [values["f1"] for values in per_class.values() if values["support"]]
    majority_role = max(ROLES, key=lambda role: per_class[role]["support"]) if count else None
    return {
        "evaluated_count": count, "total_nodes": len(nodes), "coverage": count / len(nodes) if nodes else 0.0,
        "accuracy": sum(confusion[role][role] for role in ROLES) / count if count else None,
        "macro_f1": sum(supported) / len(supported) if supported else None,
        "per_class": per_class, "confusion_matrix": confusion,
        "confusion_axes": {"rows": "supplied_verified_role", "columns": "current_predicted_role"},
        "baseline": {"name": "majority_label_on_evaluated_subset", "role": majority_role,
                     "accuracy": per_class[majority_role]["support"] / count if count else None,
                     "note": "Descriptive baseline on the same labelled subset, not an independent held-out benchmark."},
        "benchmark_split": {"scheme": "evaluation_only", "training_count": 0, "evaluation_count": count,
                            "held_out_status": "unknown", "model_retrained": False},
        "label_independence": "unknown", "label_status": "analyst_asserted_not_independently_verified",
        "notice": NOTICE + " If labels influenced rule selection, these results are not independent validation.",
    }


def empty_casebook(analysis: dict) -> dict:
    return {"schema_version": 1, "dataset_fingerprint": dataset_fingerprint(analysis),
            "fingerprint_scope": "source_records" if (analysis.get("meta") or {}).get("dataset_fingerprint") else "observed_analysis_data",
            "revision": 0, "reviews": [], "labels": [], "history": [],
            "evaluation": evaluate_labels(analysis, []), "notice": NOTICE}


def _evidence(value: Any, nodes: dict[str, dict]) -> list[dict]:
    if not isinstance(value, list) or len(value) > 50:
        raise ValueError("evidence must be a list with at most 50 records")
    result = []
    seen = set()
    for record in value:
        allowed = {"kind", "source_reference", "summary", "related_gids", "id", "verification"}
        if not isinstance(record, dict) or not {"kind", "source_reference", "summary"} <= set(record) or set(record) - allowed:
            raise ValueError("Evidence accepts kind, source_reference, summary and related_gids only; do not add identity fields")
        if record["kind"] not in EVIDENCE_KINDS:
            raise ValueError("Evidence kind must be ownership, control, transaction or other")
        related = record.get("related_gids", [])
        if not isinstance(related, list) or len(related) > 50:
            raise ValueError("Evidence related_gids must contain at most 50 known account IDs")
        keys = [_known_gid(gid, nodes) for gid in related]
        if len(set(keys)) != len(keys):
            raise ValueError("Evidence related_gids contains duplicate IDs")
        item = {"kind": record["kind"],
                "source_reference": _text(record["source_reference"], "evidence.source_reference", maximum=1000, required=True),
                "summary": _text(record["summary"], "evidence.summary", maximum=3000, required=True),
                "related_gids": sorted(keys, key=int), "verification": "analyst_asserted"}
        item["id"] = "evidence-" + hashlib.sha256(_json(item).encode("utf-8")).hexdigest()[:20]
        if record.get("id", item["id"]) != item["id"] or record.get("verification", "analyst_asserted") != "analyst_asserted":
            raise ValueError("Evidence identifier or verification status is inconsistent")
        if item["id"] in seen:
            raise ValueError("Duplicate evidence record")
        seen.add(item["id"])
        result.append(item)
    return sorted(result, key=lambda item: item["id"])


def _review_record(nodes: dict[str, dict], record: dict) -> dict:
    allowed = {"gid", "status", "reviewer", "source_reference", "notes", "verified_role", "evidence", "revision",
               "predicted_role_at_review"}
    if not isinstance(record, dict) or "gid" not in record or set(record) - allowed:
        raise ValueError("Review contains missing gid or unsupported fields")
    key = _known_gid(record["gid"], nodes)
    status = record.get("status", "unreviewed")
    if status not in STATUSES:
        raise ValueError("status must be unreviewed, in_review, supported or rejected")
    verified = record.get("verified_role")
    if verified is not None and verified not in ROLES:
        raise ValueError("verified_role must be null or one of the six supported roles")
    if verified is not None and status not in {"supported", "rejected"}:
        raise ValueError("verified_role requires a finalized supported/rejected review")
    # Preserve the hypothesis an analyst actually reviewed when rules change.
    # Metrics still compare supplied labels with the current predictions.
    predicted = record.get("predicted_role_at_review", nodes[key]["role"])
    if predicted not in ROLES:
        raise ValueError("predicted_role_at_review must be one of the six supported roles")
    if status == "supported" and verified is not None and verified != predicted:
        raise ValueError("A supported prediction must match verified_role; use rejected for a different verified role")
    if status == "rejected" and verified == predicted:
        raise ValueError("A rejected prediction cannot use the same verified_role")
    revision = record.get("revision", 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("Review revision must be a nonnegative integer")
    return {"gid": key, "status": status,
            "reviewer": _text(record.get("reviewer", ""), "reviewer", maximum=120, required=status != "unreviewed"),
            "source_reference": _text(record.get("source_reference", ""), "source_reference", maximum=1000,
                                      required=status in {"supported", "rejected"} or verified is not None),
            "notes": _text(record.get("notes", ""), "notes", maximum=5000),
            "verified_role": verified, "predicted_role_at_review": predicted,
            "evidence": _evidence(record.get("evidence", []), nodes), "revision": revision}


def _existing_casebook(analysis: dict, existing: Any) -> dict:
    if existing is None:
        return empty_casebook(analysis)
    if not isinstance(existing, dict):
        raise ValueError("existing_casebook must be a casebook object or null")
    _json(existing)
    if existing.get("schema_version") != 1:
        raise ValueError("Unsupported casebook schema_version")
    if existing.get("dataset_fingerprint") != dataset_fingerprint(analysis):
        raise ValueError("Casebook belongs to a different dataset; reviews were not merged")
    revision = existing.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("Casebook revision must be a nonnegative integer")
    nodes = _nodes(analysis)
    records = existing.get("reviews", [])
    if not isinstance(records, list):
        raise ValueError("casebook.reviews must be a list")
    reviews = [_review_record(nodes, record) for record in records]
    if len({record["gid"] for record in reviews}) != len(reviews):
        raise ValueError("Casebook contains duplicate review IDs")
    if any(record["revision"] > revision for record in reviews):
        raise ValueError("Review revision exceeds casebook revision")
    labels = _labels(analysis, existing.get("labels", []))
    expected_labels = sorted(({field: record[field] for field in LABEL_FIELDS}
                              for record in reviews if record["verified_role"] is not None),
                             key=lambda label: int(label["gid"]))
    if labels != expected_labels:
        raise ValueError("Casebook labels are inconsistent with finalized review records")
    history = existing.get("history", [])
    if not isinstance(history, list):
        raise ValueError("casebook.history must be a list")
    result = empty_casebook(analysis)
    result.update(revision=revision, reviews=reviews, labels=labels, history=deepcopy(history), evaluation=evaluate_labels(analysis, labels))
    return result


def update_review(analysis: dict, existing_casebook: dict | None, payload: dict) -> dict:
    """Validate and apply one review or a batch of explicit imported labels.

    Default action is ``set_review``. ``import_labels`` accepts ``labels`` and
    upserts those IDs, rejecting duplicates within the import. Omitted review
    fields are preserved; explicit ``verified_role: null`` removes that label.
    The optional ``expected_revision`` rejects stale writes. ``refresh`` only
    revalidates and recomputes evaluation, without advancing the revision.
    """
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    _json(payload)
    casebook = _existing_casebook(analysis, existing_casebook)
    expected = payload.get("expected_revision")
    if "expected_revision" in payload and (isinstance(expected, bool) or not isinstance(expected, int) or expected != casebook["revision"]):
        raise ValueError("Stale casebook revision; reload before saving")
    action = payload.get("action", "set_review")
    nodes = _nodes(analysis)
    reviews = {record["gid"]: record for record in casebook["reviews"]}
    labels = {record["gid"]: record for record in casebook["labels"]}
    next_revision = casebook["revision"] + 1
    changes = []
    if action == "refresh":
        if set(payload) - {"action", "expected_revision"}:
            raise ValueError("refresh accepts no review changes")
        return casebook
    if action == "import_labels":
        if set(payload) - {"action", "labels", "expected_revision"} or "labels" not in payload:
            raise ValueError("import_labels requires labels and no unsupported fields")
        incoming = _labels(analysis, payload["labels"])
        for label in incoming:
            key = label["gid"]
            previous = reviews.get(key, {"gid": key})
            status = "supported" if label["verified_role"] == nodes[key]["role"] else "rejected"
            record = _review_record(nodes, {**previous, **label, "status": status, "revision": next_revision,
                                           "predicted_role_at_review": nodes[key]["role"]})
            reviews[key], labels[key] = record, label
            changes.append({"gid": key, "status": status, "verified_role": label["verified_role"],
                            "reviewer": label["reviewer"], "source_reference": label["source_reference"],
                            "previous_record": deepcopy(previous) if "revision" in previous else None,
                            "record": deepcopy(record)})
    elif action == "set_review":
        allowed = {"action", "expected_revision", "gid", "status", "reviewer", "source_reference", "notes", "verified_role", "evidence"}
        if set(payload) - allowed or "gid" not in payload:
            raise ValueError("set_review contains missing gid or unsupported fields")
        key = _known_gid(payload["gid"], nodes)
        values = {field: value for field, value in payload.items() if field not in {"action", "expected_revision"}}
        previous = reviews.get(key, {"gid": key})
        if "status" in payload or "verified_role" in payload:
            values["predicted_role_at_review"] = nodes[key]["role"]
        record = _review_record(nodes, {**previous, **values, "revision": next_revision})
        reviews[key] = record
        if record["verified_role"] is not None:
            labels[key] = {field: record[field] for field in LABEL_FIELDS}
        elif "verified_role" in payload:
            labels.pop(key, None)
        changes.append({"gid": key, "status": record["status"], "verified_role": record["verified_role"],
                        "reviewer": record["reviewer"], "source_reference": record["source_reference"],
                        "previous_record": deepcopy(previous) if "revision" in previous else None,
                        "record": deepcopy(record)})
    else:
        raise ValueError("action must be set_review, import_labels or refresh")
    if not changes:
        return casebook
    casebook["reviews"] = sorted(reviews.values(), key=lambda record: int(record["gid"]))
    casebook["labels"] = sorted(labels.values(), key=lambda record: int(record["gid"]))
    casebook["revision"] = next_revision
    casebook["history"].append({"revision": next_revision, "action": action, "changes": changes,
                                "provenance": "local_analyst_assertion_not_tamper_proof"})
    casebook["evaluation"] = evaluate_labels(analysis, casebook["labels"])
    return casebook


def labels_csv_template(analysis: dict) -> str:
    """Export exact IDs with empty annotation fields, never predicted labels."""
    nodes = _nodes(analysis)
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=LABEL_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows({"gid": key, "verified_role": "", "source_reference": "", "reviewer": ""}
                    for key in sorted(nodes, key=int))
    return stream.getvalue()


def parse_labels_csv(analysis: dict, text: str) -> list[dict]:
    """Read a label template safely; skip only wholly unfilled known-ID rows.

    Every row's ID is checked, including blank template rows. Duplicate IDs,
    unknown IDs, partial annotations, wrong headers, and malformed CSV fail.
    """
    if not isinstance(text, str) or len(text) > 10_000_000:
        raise ValueError("CSV labels must be text of at most 10 MB")
    nodes = _nodes(analysis)
    records, seen = [], set()
    try:
        reader = csv.DictReader(StringIO(text.lstrip("\ufeff")), strict=True)
        if reader.fieldnames is None or len(reader.fieldnames) != len(LABEL_FIELDS) or set(reader.fieldnames) != set(LABEL_FIELDS):
            raise ValueError("Label CSV headers must be exactly " + ",".join(LABEL_FIELDS))
        for row in reader:
            if set(row) != set(LABEL_FIELDS) or any(value is None for value in row.values()):
                raise ValueError("Malformed label CSV row")
            key = _known_gid(row["gid"], nodes)
            if key in seen:
                raise ValueError(f"Duplicate label CSV gid: {key}")
            seen.add(key)
            row = {field: value.strip() for field, value in row.items()}
            row["gid"] = key
            if not any(row[field] for field in LABEL_FIELDS if field != "gid"):
                continue
            records.append(row)
    except csv.Error as exc:
        raise ValueError(f"Invalid label CSV: {exc}") from exc
    return _labels(analysis, records)


def export_casebook(casebook: dict) -> str:
    """Serialize the complete review/evaluation record without NaN or ID loss."""
    if not isinstance(casebook, dict) or casebook.get("schema_version") != 1:
        raise ValueError("A version 1 casebook is required")
    _json(casebook)
    return json.dumps(casebook, ensure_ascii=False, indent=2, allow_nan=False)
