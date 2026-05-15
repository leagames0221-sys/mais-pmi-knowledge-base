"""orchestrator module (internal ADR § 4 順守、 LangGraph state graph DAG)。

Week 2 active:
- build_state_graph.py: 9 node DAG (internal ADR § 4 diagram literal 順守、 description「7 node」 → 9 node 実装 = drift evidence、 logbook 記録) + conditional routing + multi-hop traversal helper

module boundaries 越境境界線 3 段階 順守:
- 段階 1 OS-primitives: langgraph >=1.2.0,<2.0 + langgraph-checkpoint + langchain-core (CVE-2026-28277 元削除 pin、 T3/T4 inherit)
- 段階 2 business logic: 9 node 業務 logic + conditional routing + multi-hop traversal (literal 自作)
"""
from .build_state_graph import (
    DEFAULT_MAX_HOPS,
    DEFAULT_WEIGHT_DECAY,
    OrchestratorState,
    build_state_graph,
    multi_hop_traverse,
)

__all__ = [
    "DEFAULT_MAX_HOPS",
    "DEFAULT_WEIGHT_DECAY",
    "OrchestratorState",
    "build_state_graph",
    "multi_hop_traverse",
]
