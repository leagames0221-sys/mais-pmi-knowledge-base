"""retrieval module。

Week 2 active:
- graphrag_native.py: 3 prompt 自作 (entity/relationship/community) + NetworkX louvain_communities thin wrapper (graph backend mode fix supersede、 leiden API dispatcher backend 不在 issue 回避) + Ontology 80% gate + PII boundary check
- jp_optimization.py: fugashi + PMI domain dictionary + entity name normalize (sub-task 3)
- multi_axis_similar_cases.py: 5 dim weighted similarity (sub-task 4)

module boundaries 越境境界線 3 段階 順守:
- 段階 1 OS-primitives use OK: networkx + fugashi + anthropic + langgraph
- 段階 2 literal 自作: 3 prompt + Ontology gate + PII boundary + 5 dim similarity + state graph
- 段階 3 framework 全体 use NG: Microsoft GraphRAG OSS 全体 / LangChain 全体 / LlamaIndex 全体 不採用
"""
