"""Session-local expert annotations and explicitly limited-sample evaluation.

Review labels are supplied by a person, never inferred from model predictions.
The fingerprint binds reviews to the normalized required input tables, including
duplicate transactions, while being independent of row order and file encoding.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
from io import StringIO
import json
import math
import numbers
import re
from typing import Mapping

import pandas as pd

from moneymap.data import REQUIRED_COLUMNS, validate_dataset
from moneymap.roles import ROLE_ORDER


UNKNOWN = "unknown"
CSV_COLUMNS = [
    "dataset_sha256", "gid", "predicted_role", "predicted_role_score",
    "predicted_priority_score", "reviewed_role", "investigation_relevant", "reviewer_note",
]
MAX_NOTE_LENGTH = 2000
MAX_CSV_BYTES = 16 * 1024 * 1024
_INTEGER = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")


@dataclass(frozen=True)
class Review:
    dataset_sha256: str
    gid: str
    reviewed_role: str = UNKNOWN
    investigation_relevant: str = UNKNOWN
    reviewer_note: str = ""


@dataclass(frozen=True)
class Evaluation:
    summary: dict
    confusion: pd.DataFrame
    by_role: pd.DataFrame
    ranking: pd.DataFrame


def _fingerprint(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("dataset_sha256: 64 кіші әріпті оналтылық таңба қажет")
    return value


def _gid(value) -> str:
    if isinstance(value, bool) or type(value).__name__ == "bool_":
        raise ValueError("gid: дәл бүтін идентификатор қажет")
    if isinstance(value, numbers.Integral):
        value = str(int(value))
    if not isinstance(value, str) or _INTEGER.fullmatch(value) is None:
        raise ValueError("gid: int64 бүтін санының дәл мәтіні қажет; float қабылданбайды")
    if not -(2**63) <= int(value) < 2**63:
        raise ValueError("gid: int64 шегінен тыс")
    return value


def _score(value, name: str) -> float:
    if isinstance(value, str):
        if _DECIMAL.fullmatch(value) is None:
            raise ValueError(f"{name}: 0–1 аралығындағы сан қажет")
    elif isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name}: 0–1 аралығындағы сан қажет")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ValueError(f"{name}: 0–1 аралығындағы шекті сан қажет")
    return result


def dataset_fingerprint(frames: dict[str, pd.DataFrame]) -> str:
    """Hash validated required values, preserving duplicate-row multiplicity."""
    validation = validate_dataset(frames)
    if not validation.valid:
        raise ValueError("Бағалау үшін жарамды үш бастапқы кесте қажет")
    digest = hashlib.sha256(b"MoneyMap normalized review dataset v1\n")
    for name, columns in REQUIRED_COLUMNS.items():
        digest.update(json.dumps([name, list(columns)], separators=(",", ":")).encode())
        rows = []
        for values in validation.frames[name][list(columns)].itertuples(index=False, name=None):
            row = []
            for column, value in zip(columns, values):
                if column == "sum_kzt":
                    row.append(float(value).hex())
                elif column == "date":
                    row.append(pd.Timestamp(value).isoformat())
                elif column == "is_seed":
                    row.append("true" if bool(value) else "false")
                else:
                    row.append(str(int(value)))
            rows.append(row)
        for row in sorted(rows):
            digest.update(b"\n")
            digest.update(json.dumps(row, separators=(",", ":")).encode())
        digest.update(b"\n\n")
    return digest.hexdigest()


def make_review(dataset_sha256: str, gid, reviewed_role=UNKNOWN,
                investigation_relevant=UNKNOWN, reviewer_note="") -> Review:
    _fingerprint(dataset_sha256)
    gid = _gid(gid)
    if reviewed_role not in (*ROLE_ORDER, UNKNOWN):
        raise ValueError("reviewed_role: алты рөлдің бірі немесе unknown қажет")
    if investigation_relevant not in ("true", "false", UNKNOWN):
        raise ValueError("investigation_relevant: true, false немесе unknown қажет")
    if not isinstance(reviewer_note, str) or len(reviewer_note) > MAX_NOTE_LENGTH:
        raise ValueError(f"reviewer_note: ең көбі {MAX_NOTE_LENGTH} таңба")
    if any(ord(char) < 32 and char not in "\t\r\n" for char in reviewer_note):
        raise ValueError("reviewer_note: жарамсыз басқару таңбасы бар")
    return Review(dataset_sha256, gid, reviewed_role, investigation_relevant, reviewer_note)


def _predictions(predictions: pd.DataFrame) -> dict[str, dict]:
    required = {"gid", "role", "role_score", "priority_score"}
    if predictions.columns.duplicated().any() or not required <= set(predictions.columns):
        raise ValueError("Болжам кестесінде gid, role, role_score, priority_score қажет")
    result = {}
    for row in predictions.to_dict("records"):
        gid = _gid(row["gid"])
        if gid in result:
            raise ValueError("Болжам кестесінде қайталанған gid бар")
        if row["role"] not in ROLE_ORDER:
            raise ValueError("Болжам кестесінде белгісіз рөл бар")
        role_score = _score(row["role_score"], "role_score")
        priority_score = _score(row["priority_score"], "priority_score")
        incoming = row.get("in_kzt", 0.0)
        if isinstance(incoming, bool) or not isinstance(incoming, numbers.Real) or not math.isfinite(incoming) or incoming < 0:
            raise ValueError("in_kzt: нөлден кем емес шекті сан қажет")
        result[gid] = {"role": row["role"], "role_score": role_score,
                       "priority_score": priority_score, "in_kzt": float(incoming)}
    return result


def ranked_gids(predictions: pd.DataFrame) -> list[str]:
    rows = _predictions(predictions)
    return sorted(rows, key=lambda gid: (-rows[gid]["priority_score"], -rows[gid]["in_kzt"], int(gid)))


def _reviews(annotations: Mapping[str, Review], dataset_sha256: str, known: set[str]) -> dict[str, Review]:
    result = {}
    for gid, review in annotations.items():
        if not isinstance(review, Review):
            raise ValueError("Сарапшы белгісінің пішімі жарамсыз")
        checked = make_review(review.dataset_sha256, review.gid, review.reviewed_role,
                              review.investigation_relevant, review.reviewer_note)
        if gid != checked.gid or gid not in known:
            raise ValueError("Сарапшы белгілерінде белгісіз немесе сәйкес емес gid бар")
        if checked.dataset_sha256 != dataset_sha256:
            raise ValueError("Белгілер басқа деректер жиынына тиесілі")
        result[gid] = checked
    return result


def _formula_note(note: str) -> bool:
    return note[:1] in ("\t", "\r", "\n") or note.lstrip(" \t\r\n").startswith(("=", "+", "-", "@"))


def _safe_note(note: str) -> str:
    # Escape initial apostrophes too, making our CSV convention reversible.
    return "'" + note if note.startswith("'") or _formula_note(note) else note


def _original_note(note: str) -> str:
    return note[1:] if note.startswith("'") and (note[1:].startswith("'") or _formula_note(note[1:])) else note


def review_csv(predictions: pd.DataFrame, dataset_sha256: str,
               annotations: Mapping[str, Review] | None = None, gids: list[str] | None = None) -> bytes:
    """Export exact textual IDs; reviewer notes are spreadsheet-formula escaped.

    Prediction columns always reflect the current run, independently of human
    labels. When opening CSV in spreadsheet software, import gid as text.
    """
    _fingerprint(dataset_sha256)
    rows = _predictions(predictions)
    reviews = _reviews(annotations or {}, dataset_sha256, set(rows))
    selected = ranked_gids(predictions) if gids is None else [_gid(gid) for gid in gids]
    if len(set(selected)) != len(selected) or not set(selected) <= set(rows):
        raise ValueError("Экспортта белгісіз немесе қайталанған gid бар")
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for gid in selected:
        row = rows[gid]
        review = reviews.get(gid, make_review(dataset_sha256, gid))
        writer.writerow([dataset_sha256, gid, row["role"], repr(row["role_score"]),
                         repr(row["priority_score"]), review.reviewed_role,
                         review.investigation_relevant, _safe_note(review.reviewer_note)])
    return output.getvalue().encode("utf-8-sig")


def read_review_csv(payload: bytes, predictions: pd.DataFrame, dataset_sha256: str) -> dict[str, Review]:
    """Validate the entire import before returning any reviews; never coerce IDs.

    Old prediction snapshots may differ after a new configuration; they are
    validated but not used as truth or substituted for current predictions.
    """
    _fingerprint(dataset_sha256)
    known = set(_predictions(predictions))
    if not isinstance(payload, bytes) or len(payload) > MAX_CSV_BYTES:
        raise ValueError("CSV UTF-8 файл болуы және 16 МБ-тан аспауы керек")
    try:
        reader = csv.reader(StringIO(payload.decode("utf-8-sig"), newline=""), strict=True)
        if next(reader, None) != CSV_COLUMNS:
            raise ValueError("CSV бағандары жүктелген үлгінің схемасымен дәл сәйкес болуы керек")
        result = {}
        for line, values in enumerate(reader, 2):
            if len(values) != len(CSV_COLUMNS):
                raise ValueError(f"CSV {line}-жол: баған саны сәйкес емес")
            row = dict(zip(CSV_COLUMNS, values))
            if row["dataset_sha256"] != dataset_sha256:
                raise ValueError(f"CSV {line}-жол: dataset_sha256 басқа деректер жиынына тиесілі")
            gid = _gid(row["gid"])
            if gid not in known:
                raise ValueError(f"CSV {line}-жол: gid ағымдағы деректерде жоқ")
            if gid in result:
                raise ValueError(f"CSV {line}-жол: gid қайталанады")
            if row["predicted_role"] not in ROLE_ORDER:
                raise ValueError(f"CSV {line}-жол: predicted_role белгісіз")
            _score(row["predicted_role_score"], "predicted_role_score")
            _score(row["predicted_priority_score"], "predicted_priority_score")
            result[gid] = make_review(dataset_sha256, gid, row["reviewed_role"],
                                      row["investigation_relevant"], _original_note(row["reviewer_note"]))
        return result
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValueError("CSV жарамды UTF-8 және үтірмен бөлінген пішімде болуы керек") from error


def evaluate_reviews(predictions: pd.DataFrame, dataset_sha256: str,
                     annotations: Mapping[str, Review], k: int = 20) -> Evaluation:
    """Compare only explicit labels; unreviewed cases never become negatives.

    Macro F1 averages classes occurring in reviewed truth OR its predictions.
    Full precision@k is returned only when the entire top-k has known relevance.
    Partial results expose assessed-only precision and bounds, not full precision.
    """
    _fingerprint(dataset_sha256)
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k оң бүтін сан болуы керек")
    predictions_by_gid = _predictions(predictions)
    reviews = _reviews(annotations, dataset_sha256, set(predictions_by_gid))
    confusion = pd.DataFrame(0, index=pd.Index(ROLE_ORDER, name="reviewed_role"),
                             columns=pd.Index(ROLE_ORDER, name="predicted_role"), dtype="int64")
    for gid, review in reviews.items():
        if review.reviewed_role != UNKNOWN:
            confusion.loc[review.reviewed_role, predictions_by_gid[gid]["role"]] += 1
    n_reviewed = int(confusion.to_numpy().sum())
    correct = int(sum(confusion.loc[role, role] for role in ROLE_ORDER))
    by_role = []
    f1_values = []
    f1_labels = []
    for role in ROLE_ORDER:
        tp = int(confusion.loc[role, role])
        truth_n, predicted_n = int(confusion.loc[role].sum()), int(confusion[role].sum())
        f1 = 2 * tp / (truth_n + predicted_n) if truth_n + predicted_n else None
        if f1 is not None:
            f1_values.append(f1)
            f1_labels.append(role)
        by_role.append({"role": role, "reviewed_n": truth_n, "predicted_n": predicted_n,
                        "precision": tp / predicted_n if predicted_n else None,
                        "recall": tp / truth_n if truth_n else None, "f1": f1})
    selected = ranked_gids(predictions)[:k]
    ranking_rows = []
    for rank, gid in enumerate(selected, 1):
        review = reviews.get(gid)
        ranking_rows.append({"rank": rank, "gid": gid,
                             "priority_score": predictions_by_gid[gid]["priority_score"],
                             "investigation_relevant": review.investigation_relevant if review else UNKNOWN})
    assessed = sum(row["investigation_relevant"] != UNKNOWN for row in ranking_rows)
    relevant = sum(row["investigation_relevant"] == "true" for row in ranking_rows)
    count = len(selected)
    summary = {
        "dataset_sha256": dataset_sha256, "n_nodes": len(predictions_by_gid),
        "role_reviewed_n": n_reviewed, "role_correct_n": correct,
        "role_coverage": n_reviewed / len(predictions_by_gid) if predictions_by_gid else 0.0,
        "accuracy": correct / n_reviewed if n_reviewed else None,
        "macro_f1": sum(f1_values) / len(f1_values) if f1_values else None,
        "macro_f1_labels": f1_labels,
        "requested_k": k, "actual_k": count, "relevance_assessed_n": assessed,
        "relevant_n": relevant, "unassessed_n": count - assessed,
        "relevance_coverage": assessed / count if count else 0.0,
        "assessed_precision_at_k": relevant / assessed if assessed else None,
        "precision_at_k": relevant / count if count and assessed == count else None,
        "precision_at_k_lower_bound": relevant / count if count else None,
        "precision_at_k_upper_bound": (relevant + count - assessed) / count if count else None,
    }
    return Evaluation(summary, confusion, pd.DataFrame(by_role),
                      pd.DataFrame(ranking_rows, columns=["rank", "gid", "priority_score", "investigation_relevant"]))
