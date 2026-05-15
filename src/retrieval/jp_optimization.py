"""ja_JP morpheme analysis + PMI domain dictionary

module boundaries 越境境界線 3 段階 順守:
- 段階 1 OS-primitives: fugashi + unidic-lite
- 段階 2 business logic: PMI domain dictionary 33+ canonical terms + surface form variants + entity name normalize (literal 自作)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Optional

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall inherit)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8") # type: ignore[attr-defined]
    except Exception:
        pass


# ============================================================================
# PMI domain dictionary (33+ canonical terms、 literal 自作、 module boundaries 段階 2)
# canonical form → surface form variants (entity name normalize + extract_pmi_terms 用)
# ============================================================================

PMI_DOMAIN_TERMS: dict[str, list[str]] = {
    # M&A 統合 type
    "tuck-in": ["tuck in", "tuckin", "タックイン", "タックイン買収"],
    "standalone": ["スタンドアロン", "独立運営", "stand alone"],
    "merger_of_equals": ["対等合併", "merger of equals", "MoE"],
    "asset_purchase": ["事業譲渡", "アセットパーチェス", "asset purchase"],
    # PMI lifecycle
    "Day-1": ["Day 1", "Day1", "DAY1", "デイワン", "クロージング初日", "Day-One"],
    "Day-100": ["Day 100", "Day100", "DAY100", "100 日", "100日", "Day-Hundred"],
    "Day-N": ["Day N", "DayN"],
    "DD": ["デューデリ", "デューディリジェンス", "due diligence", "Due Diligence"],
    "retrospective": ["振り返り", "事後評価", "振返り", "Day-N retrospective"],
    # synergy
    "cost synergy": ["コストシナジー", "コスト・シナジー", "cost synergies", "費用削減効果"],
    "revenue synergy": ["売上シナジー", "売上・シナジー", "revenue synergies", "売上向上効果"],
    "synergies": ["シナジー", "synergy", "相乗効果"],
    "organic_growth": ["organic growth", "オーガニックグロース", "内的成長"],
    # 統合 layer
    "文化統合": ["culture integration", "カルチャーインテグレーション", "組織文化統合"],
    "制度統合": ["人事制度統合", "HR integration"],
    "システム統合": ["IT 統合", "system integration", "IT システム統合"],
    "業務統合": ["operational integration", "業務プロセス統合"],
    # ownership / 経営形態
    "同族経営": ["同族企業", "family business", "ファミリービジネス"],
    "創業者経営": ["創業家経営", "オーナー経営"],
    "雇われ経営": ["プロ経営", "professional management"],
    "大手子会社": ["大手企業子会社", "子会社", "subsidiary"],
    # KPI
    "EBITDA": ["イービットダ", "イービットディーエー"],
    "KPI": ["主要業績指標", "Key Performance Indicator"],
    "retention": ["リテンション", "従業員定着率", "残留率"],
    "engagement": ["エンゲージメント", "従業員意識"],
    # 組織
    "組合": ["労働組合", "ユニオン", "union"],
    "取締役会": ["board of directors", "ボード"],
    "株主総会": ["AGM", "annual general meeting"],
    "担当者引継": ["引継ぎ", "ハンドオーバー", "handover"],
    # MAIS 固有 + Assistant
    "MAIS": ["MAIS", "MAIS", "MAIS"],
    "Assistant": ["アシスタント", "アシスタント"],
    "PMI": ["post-merger integration", "ポストマージャーインテグレーション", "統合後経営"],
}


# reverse lookup table: lower-cased surface form → canonical (entity normalize 用)
def _build_reverse_lookup() -> dict[str, str]:
    table: dict[str, str] = {}
    for canonical, variants in PMI_DOMAIN_TERMS.items():
        table[canonical.lower()] = canonical
        for variant in variants:
            table[variant.lower()] = canonical
    return table


_SURFACE_TO_CANONICAL: dict[str, str] = _build_reverse_lookup()


# ============================================================================
# Token schema (fugashi 出力 + PMI domain term flag)
# ============================================================================


@dataclass(frozen=True)
class Token:
    """fugashi morpheme + PMI domain term tagged 結果。"""

    surface: str # 表層形 (元の文字列)
    base_form: str # 原形 (lemma)
    pos: str # 品詞 (Part of Speech)
    is_pmi_domain_term: bool
    canonical_form: Optional[str] = None # PMI canonical form (term 検出時のみ)


# ============================================================================
# Tagger management (singleton、 fugashi.Tagger init は 1 回のみ + lazy)
# ============================================================================

_TAGGER_CACHE: Any = None


def get_tagger() -> Any:
    """fugashi.Tagger lazy singleton init (process 単位 1 回のみ)。

    Raises:
        RuntimeError: fugashi or unidic-lite not installed
    """
    global _TAGGER_CACHE
    if _TAGGER_CACHE is not None:
        return _TAGGER_CACHE
    try:
        import fugashi # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "fugashi not installed。 "
            "Run: pip install 'fugashi[unidic-lite]>=1.3,<2.0'"
        ) from exc
    _TAGGER_CACHE = fugashi.Tagger()
    return _TAGGER_CACHE


def reset_tagger_cache() -> None:
    """singleton cache clear (test 用)。"""
    global _TAGGER_CACHE
    _TAGGER_CACHE = None


# ============================================================================
# Entity name normalize
# ============================================================================


def normalize_entity_name(name: str) -> str:
    """surface form → canonical form mapping。

    PMI domain term の場合 canonical 返却、 それ以外は 入力 strip のみ。
    例: "大手子会社" → "大手子会社" / "子会社" → "大手子会社" / "subsidiary" → "大手子会社"
    """
    if not name:
        return name
    stripped = name.strip()
    canonical = _SURFACE_TO_CANONICAL.get(stripped.lower())
    return canonical if canonical else stripped


def lookup_pmi_term(surface: str) -> Optional[str]:
    """surface form が PMI domain term の場合 canonical 返却、 含まない場合 None。"""
    if not surface:
        return None
    return _SURFACE_TO_CANONICAL.get(surface.strip().lower())


def is_pmi_term(surface: str) -> bool:
    """surface form が PMI domain term か boolean 判定。"""
    return lookup_pmi_term(surface) is not None


# ============================================================================
# Tokenize (fugashi tagger 経由)
# ============================================================================


def _extract_feature_attr(word: Any, *attr_names: str) -> Optional[str]:
    """fugashi word.feature の attribute を safe 抽出 (unidic version 差異対応)。"""
    feature = getattr(word, "feature", None)
    if feature is None:
        return None
    for attr in attr_names:
        value = getattr(feature, attr, None)
        if value is not None and value != "*":
            return str(value)
    return None


def tokenize(text: str) -> list[Token]:
    """text → list[Token] (fugashi morpheme + PMI domain term tagged)。

    Raises:
        RuntimeError: fugashi/unidic-lite not installed
    """
    if not text:
        return []
    tagger = get_tagger()
    tokens: list[Token] = []
    for word in tagger(text):
        surface = str(getattr(word, "surface", ""))
        base_form = _extract_feature_attr(word, "lemma", "orth") or surface
        pos = _extract_feature_attr(word, "pos1") or "UNK"
        canonical = lookup_pmi_term(surface)
        tokens.append(
            Token(
                surface=surface,
                base_form=base_form,
                pos=pos,
                is_pmi_domain_term=canonical is not None,
                canonical_form=canonical,
            )
        )
    return tokens


def extract_pmi_terms(text: str) -> list[str]:
    """text 内 PMI domain term の canonical form list (重複除去 + 出現順保持)。

    multi-word term (例: "due diligence" 2 単語、 "post-merger integration" 3 単語) も
    surface-form substring scan で literal 検出可能 (fugashi 分割境界 非依存)。
    fugashi 起動 不要 (purely string scan)、 light verify use OK。
    """
    if not text:
        return []
    text_lower = text.lower()
    seen: set[str] = set()
    found: list[tuple[int, str]] = [] # (first_match_offset, canonical)
    for canonical, variants in PMI_DOMAIN_TERMS.items():
        for form in [canonical, *variants]:
            offset = text_lower.find(form.lower())
            if offset >= 0 and canonical not in seen:
                found.append((offset, canonical))
                seen.add(canonical)
                break
    found.sort(key=lambda x: x[0])
    return [canonical for _, canonical in found]


__all__ = [
    "PMI_DOMAIN_TERMS",
    "Token",
    "get_tagger",
    "reset_tagger_cache",
    "normalize_entity_name",
    "lookup_pmi_term",
    "is_pmi_term",
    "tokenize",
    "extract_pmi_terms",
]
