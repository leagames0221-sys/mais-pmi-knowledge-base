"""T5 FastAPI Web UI module。

module boundaries 段階 1 OS-primitives: FastAPI + Jinja2 (literal use OK、 T1-T4 inherit)
module boundaries 段階 2 business logic: 黒金 brand + Assistant dialogue route + similar case panel + knowledge base search (literal 自作)

共通 doctrine inherit:
- brand: MAIS / 黒金 (#0a0a0a + #d4af37) / Noto Sans JP / 年輪 motif
- 動画 pipeline: cross-PJ universal video-pipeline SSoT (英字 brand 名 カタカナ化必須、 narration mode trap 防御)
"""
from .app import app

__all__ = ["app"]
