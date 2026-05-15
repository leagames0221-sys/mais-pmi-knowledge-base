"""T5 Operational DB: PII redact 済 6 type を JSONL で保管 (internal ADR + T1 inherit pattern)。

embedding / retrieval / assistant engine が literal 読む唯一の data source。 vault と link は
pmi_id / dec_id / out_id / pat_id / ref_id / lil_id のみ。 漏洩しても仮名加工情報 =
個人情報保護法 2026 改正方針で報告義務 ZERO。

移植段階 = sqlite + index pattern (doctrine: future-proof)、 PoC = JSONL linear scan で literal 充分 (1000 entry 未満想定)。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, TypeVar

from ..schema.types import (
    Decision,
    AssistantQuery,
    Outcome,
    Pattern,
    PMICase,
    ReferencePaper,
)

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall inherit)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


T = TypeVar("T")


def _data_dir() -> Path:
    """env DATA_DIR override path (test 環境 + 移植段階 顧客 sandbox path、 doctrine: future-proof)。"""
    return Path(os.environ.get("DATA_DIR", "./data"))


def _op_dir() -> Path:
    return _data_dir() / "operational"


# ============================================================================
# Table → file mapping (6 type)
# ============================================================================

_TABLE_FILE: dict[str, str] = {
    "pmi_case": "pmi_cases.jsonl",
    "decision": "decisions.jsonl",
    "outcome": "outcomes.jsonl",
    "pattern": "patterns.jsonl",
    "reference_paper": "reference_papers.jsonl",
    "assistant_query": "assistant_queries.jsonl",
}

_TABLE_ID_KEY: dict[str, str] = {
    "pmi_case": "pmi_id",
    "decision": "dec_id",
    "outcome": "out_id",
    "pattern": "pat_id",
    "reference_paper": "ref_id",
    "assistant_query": "lil_id",
}


def _table_path(table: str) -> Path:
    if table not in _TABLE_FILE:
        raise ValueError(f"unknown table: {table!r}、 valid = {sorted(_TABLE_FILE)}")
    return _op_dir() / _TABLE_FILE[table]


# ============================================================================
# Generic load / save (linear scan JSONL、 doctrine: waste-zero + doctrine: future-proof)
# ============================================================================


def _load_all_raw(table: str) -> dict[str, dict[str, Any]]:
    """JSONL → dict[id, record] (id_key 経由)。 file 不在 = {}。"""
    path = _table_path(table)
    if not path.exists():
        return {}
    id_key = _TABLE_ID_KEY[table]
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # corrupted line skip (defensive、 silent ではあるが next valid record まで進む)
        if id_key in rec:
            out[rec[id_key]] = rec
    return out


def _save_all_raw(table: str, records: dict[str, dict[str, Any]]) -> None:
    """全 records JSONL に literal rewrite (atomic = tmp + rename pattern)。"""
    path = _table_path(table)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for rec in records.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp_path.replace(path)  # atomic rename (POSIX + Windows でも 同一 device で literal atomic)


def _store_typed(table: str, item: Any) -> None:
    """Pydantic model → JSONL store (upsert by id_key)。"""
    records = _load_all_raw(table)
    id_key = _TABLE_ID_KEY[table]
    rec = item.model_dump(mode="json")
    if id_key not in rec:
        raise ValueError(f"{table} record missing {id_key}: {rec}")
    records[rec[id_key]] = rec
    _save_all_raw(table, records)


def _get_typed(table: str, item_id: str, model_cls: Callable[..., T]) -> T | None:
    """id_key → Pydantic model 復元 (未 match = None)。"""
    raw = _load_all_raw(table).get(item_id)
    if raw is None:
        return None
    return model_cls(**raw)  # type: ignore[call-arg]


def _list_typed(table: str, model_cls: Callable[..., T], limit: int | None = None) -> list[T]:
    """全 records → Pydantic model list (順序: insertion order maintained by dict)。"""
    raw_items = list(_load_all_raw(table).values())
    if limit is not None:
        raw_items = raw_items[:limit]
    return [model_cls(**rec) for rec in raw_items]  # type: ignore[call-arg]


# ============================================================================
# Public API: per-type store + get + list (6 type)
# ============================================================================


# PMICase ----------------------------------------------------------


def store_pmi_case(case: PMICase) -> None:
    _store_typed("pmi_case", case)


def get_pmi_case(pmi_id: str) -> PMICase | None:
    return _get_typed("pmi_case", pmi_id, PMICase)


def list_pmi_cases(limit: int | None = None) -> list[PMICase]:
    return _list_typed("pmi_case", PMICase, limit)


# Decision ----------------------------------------------------------


def store_decision(dec: Decision) -> None:
    _store_typed("decision", dec)


def get_decision(dec_id: str) -> Decision | None:
    return _get_typed("decision", dec_id, Decision)


def list_decisions(limit: int | None = None) -> list[Decision]:
    return _list_typed("decision", Decision, limit)


# Outcome ----------------------------------------------------------


def store_outcome(out: Outcome) -> None:
    _store_typed("outcome", out)


def get_outcome(out_id: str) -> Outcome | None:
    return _get_typed("outcome", out_id, Outcome)


def list_outcomes(limit: int | None = None) -> list[Outcome]:
    return _list_typed("outcome", Outcome, limit)


# Pattern ----------------------------------------------------------


def store_pattern(pat: Pattern) -> None:
    _store_typed("pattern", pat)


def get_pattern(pat_id: str) -> Pattern | None:
    return _get_typed("pattern", pat_id, Pattern)


def list_patterns(limit: int | None = None) -> list[Pattern]:
    return _list_typed("pattern", Pattern, limit)


# ReferencePaper ----------------------------------------------------------


def store_reference_paper(ref: ReferencePaper) -> None:
    _store_typed("reference_paper", ref)


def get_reference_paper(ref_id: str) -> ReferencePaper | None:
    return _get_typed("reference_paper", ref_id, ReferencePaper)


def list_reference_papers(limit: int | None = None) -> list[ReferencePaper]:
    return _list_typed("reference_paper", ReferencePaper, limit)


# AssistantQuery ----------------------------------------------------------


def store_assistant_query(lq: AssistantQuery) -> None:
    _store_typed("assistant_query", lq)


def get_assistant_query(lil_id: str) -> AssistantQuery | None:
    return _get_typed("assistant_query", lil_id, AssistantQuery)


def list_assistant_queries(limit: int | None = None) -> list[AssistantQuery]:
    return _list_typed("assistant_query", AssistantQuery, limit)


__all__ = [
    "store_pmi_case", "get_pmi_case", "list_pmi_cases",
    "store_decision", "get_decision", "list_decisions",
    "store_outcome", "get_outcome", "list_outcomes",
    "store_pattern", "get_pattern", "list_patterns",
    "store_reference_paper", "get_reference_paper", "list_reference_papers",
    "store_assistant_query", "get_assistant_query", "list_assistant_queries",
]
