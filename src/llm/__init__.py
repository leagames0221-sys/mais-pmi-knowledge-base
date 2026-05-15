"""LLMProvider Protocol module (internal ADR § 6 順守、 T4 src/llm/ inherit pattern)。

3 method (complete + count_tokens + health_check) Protocol で
MockProvider (Week 2 default) + ClaudeProvider + OllamaProvider (Week 3 末) swap path 確保。
"""
from .provider import ClaudeProvider, LLMProvider, MockProvider, OllamaProvider

__all__ = ["ClaudeProvider", "LLMProvider", "MockProvider", "OllamaProvider"]
