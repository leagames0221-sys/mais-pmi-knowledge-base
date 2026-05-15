"""LLMProvider Protocol SSoT

3 method (complete + count_tokens + health_check) で
MockProvider (Week 2 default) + ClaudeProvider + OllamaProvider (Week 3 末 8 gate gate 8) swap path 確保。
Week 2 = MockProvider stub のみ active、 Claude/Ollama 実 call は Week 3 末段階。
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """3-method Protocol"""

    def complete(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        """LLM completion call。 system + user prompt → assistant text response。"""
        ...

    def count_tokens(self, text: str) -> int:
        """text → token count estimate (8 gate gate 7 consumer laptop completion 監視用)。"""
        ...

    def health_check(self) -> bool:
        """provider 接続健全性 check (Week 3 末 swap path verify 用)。"""
        ...


class MockProvider:
    """test 用 deterministic fixture provider (Week 2 default、 graphrag_native + orchestrator test 用)。

    fixture = {key: response} dict、 system prompt or user prompt に key が含まれれば response 返却。
    fixture 未 match 時 = "[]" (空 JSON array) 返却 (entity/relationship extraction default-safe)。
    """

    def __init__(self, fixture: dict[str, str] | None = None) -> None:
        self.fixture: dict[str, str] = fixture or {}
        self.call_log: list[dict[str, object]] = []

    def complete(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        self.call_log.append(
            {
                "prompt_head": prompt[:200],
                "system_head": system[:200],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        for key, response in self.fixture.items():
            if key in system or key in prompt:
                return response
        return "[]"

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def health_check(self) -> bool:
        return True


class ClaudeProvider:
    """anthropic SDK 経由 ClaudeProvider (Week 3 末 8 gate gate 8 swap path verify foundation)。

    Week 3 = lazy import + Protocol compatibility のみ verify、 実 call は user 工数 (ANTHROPIC_API_KEY .env 配備後)。
    Week 4 移植段階 = literal anthropic.messages.create + claude-haiku-4-5 default + claude-sonnet-4-6 escalation path。
    """

    def __init__(self, model: str = "claude-haiku-4-5", api_key: Optional[str] = None) -> None:
        self.model = model
        self.api_key = api_key
        self._client: object = None

    def _get_client(self) -> object:
        if self._client is not None:
            return self._client
        try:
            import anthropic # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "anthropic SDK not installed。 "
                "Run: pip install 'anthropic>=0.100,<1.0'"
            ) from exc
        self._client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else anthropic.Anthropic()
        return self._client

    def complete(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        client = self._get_client()
        response = client.messages.create( # type: ignore[attr-defined]
            model=self.model,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # extract text from content blocks
        text_parts = [block.text for block in response.content if hasattr(block, "text")]
        return "".join(text_parts)

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4) # rough estimate、 実 API は client.count_tokens 利用 (Week 4 active)

    def health_check(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception:
            return False


class OllamaProvider:
    """Ollama 経由 local LLM swap path (Week 3 末 8 gate gate 8 swap path verify foundation)。

    Week 3 = stub + Protocol compatibility のみ verify、 実 call は user 工数 (Ollama install + model pull)。
    Week 4 移植段階 = literal HTTP request to localhost:11434/api/generate。
    """

    def __init__(
        self,
        model: str = "llama3:8b",
        endpoint: str = "http://localhost:11434",
        seed: Optional[int] = None,
    ) -> None:
        self.model = model
        self.endpoint = endpoint
        self.seed = seed

    def complete(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> str:
        try:
            import urllib.request
        except ImportError as exc:
            raise RuntimeError("urllib required for OllamaProvider") from exc
        import json as _json
        options: dict[str, object] = {"temperature": temperature, "num_predict": max_tokens}
        if self.seed is not None:
            options["seed"] = self.seed
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "options": options,
            "stream": False,
        }
        req = urllib.request.Request(
            f"{self.endpoint}/api/generate",
            data=_json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        return str(data.get("response", ""))

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def health_check(self) -> bool:
        try:
            import urllib.request
            with urllib.request.urlopen(f"{self.endpoint}/api/tags", timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False
