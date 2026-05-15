"""assistant module。

Week 3 active:
- dialogue_orchestrate.py: AssistantDialogueRequest schema + assistant_recommend listwise CoT + AssistantCounter persistent + audit log emit

module boundaries 越境境界線 3 段階 順守:
- 段階 1 OS-primitives: anthropic SDK (literal use OK)
- 段階 2 business logic: listwise CoT prompt + counter persistence + audit log emit (literal 自作)
"""
from .dialogue_orchestrate import (
    LISTWISE_COT_SYSTEM_PROMPT,
    AssistantCounter,
    AssistantDialogueRequest,
    emit_assistant_audit,
    assistant_recommend,
)

__all__ = [
    "LISTWISE_COT_SYSTEM_PROMPT",
    "AssistantCounter",
    "AssistantDialogueRequest",
    "emit_assistant_audit",
    "assistant_recommend",
]
