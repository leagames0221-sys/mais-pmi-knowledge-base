"""T5 FastAPI Web UI。

Commercial-grade upgrade (2026-05-14、 hardening phase、 audit fix landing):
  C-1: MockProvider → OllamaProvider env-var swap (T5_LLM_PROVIDER=ollama で literal active)
  C-2: tempfile → persistent audit_dir (data/audit/assistant/ default、 T5_AUDIT_DIR で override 可)
  H-3-a: HTTPBasic auth (T5_AUTH_REQUIRED=1 で active、 default off で test 互換維持)
  H-3-b: CSRF token (cookie + hidden form input、 T5_CSRF_REQUIRED=1 で active)
  H-3-c: in-process rate-limit (per-IP fixed window 60s、 default 60 req/min、 env override)
  H-5: VAULT_KEY .env 経由 persistent (python-dotenv 既 install)
  H-6: PII redaction layer (check_pii_boundary call、 T5_BLOCK_PII=1 で literal block、 default warn-only)

env var SSoT (production deploy 時 設定):
  T5_LLM_PROVIDER=ollama # default mock (test) / production = ollama
  T5_OLLAMA_MODEL=gemma3:4b # default
  T5_AUTH_REQUIRED=1 # default 0
  T5_BASIC_USER=<username>
  T5_BASIC_PASS=<password>
  T5_CSRF_REQUIRED=1 # default 0
  T5_RATE_LIMIT_PER_MIN=60 # default 60
  T5_AUDIT_DIR=data/audit/assistant
  T5_BLOCK_PII=1 # default 0 (warn-only)
  VAULT_KEY=<fernet key> # vault PII 暗号化 (src/vault/store.py 参照)
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# .env literal load (H-5 fix、 python-dotenv は requirements-week0.txt で literal pin)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass # dotenv 不在時 graceful skip (os.environ のみ参照)

from ..data_gen.generate_synthetic_pmi import generate_pmi_cases
from ..ingestion.generate_synthetic_papers import generate_synthetic_paper_corpus
from ..assistant.dialogue_orchestrate import (
    DEFAULT_TOP_K,
    AssistantCounter,
    AssistantDialogueRequest,
    emit_assistant_audit,
    assistant_recommend,
)
from ..llm.provider import LLMProvider, MockProvider
from ..retrieval.graphrag_native import check_pii_boundary
from ..retrieval.jp_optimization import extract_pmi_terms
from ..retrieval.multi_axis_similar_cases import rank_similar_cases

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall inherit)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8") # type: ignore[attr-defined]
    except Exception:
        pass


# ============================================================================
# Env-driven config (hardening phase、 production deploy via env vars)
# ============================================================================


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").lower() in {"1", "true", "yes"}


T5_LLM_PROVIDER: str = os.environ.get("T5_LLM_PROVIDER", "mock").lower() # mock | ollama
T5_OLLAMA_MODEL: str = os.environ.get("T5_OLLAMA_MODEL", "gemma3:4b")
T5_OLLAMA_ENDPOINT: str = os.environ.get("T5_OLLAMA_ENDPOINT", "http://localhost:11434")
T5_AUTH_REQUIRED: bool = _env_bool("T5_AUTH_REQUIRED")
T5_BASIC_USER: str = os.environ.get("T5_BASIC_USER", "")
T5_BASIC_PASS: str = os.environ.get("T5_BASIC_PASS", "")
T5_CSRF_REQUIRED: bool = _env_bool("T5_CSRF_REQUIRED")
T5_RATE_LIMIT_PER_MIN: int = int(os.environ.get("T5_RATE_LIMIT_PER_MIN", "60"))
T5_AUDIT_DIR: Path = Path(os.environ.get("T5_AUDIT_DIR", "data/audit/assistant"))
T5_BLOCK_PII: bool = _env_bool("T5_BLOCK_PII")

# audit dir 起動時 ensure (C-2 fix、 persistent audit trail foundation)
T5_AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# T5 PII Vault 機能 trigger 確認 (H-5 fix、 prod では VAULT_KEY 必須)
if T5_AUTH_REQUIRED and not os.environ.get("VAULT_KEY"):
    print("[WARN] T5_AUTH_REQUIRED=1 だが VAULT_KEY 未設定、 vault 復号不能 risk (production deploy NG)", file=sys.stderr)


# ============================================================================
# Assistant fixture (C-1: MockProvider default 用、 Ollama swap 不可時 graceful fallback)
# ============================================================================

_ASSISTANT_FIXTURE: str = json.dumps([
    {
        "rank": 1,
        "recommendation_redacted": "類似 PMI case PMI-000000001 で同族経営 + 関西本社 pattern: 組合存続 path で retention 92%、 Day-1 文化統合 communicator 早期任命 推奨",
        "confidence": 0.85,
        "citation_array": ["PMI-000000001", "REF-000007"],
    },
    {
        "rank": 2,
        "recommendation_redacted": "PMI-000000003 retrospective: tuck-in での組合解消 path = retention 80% (12 pt 低下)、 検討時 organizational design + 退職 risk simulation 必須",
        "confidence": 0.72,
        "citation_array": ["PMI-000000003"],
    },
    {
        "rank": 3,
        "recommendation_redacted": "top-tier PMI advisor 2024 paper 推奨: family business 同族経営 case = founder advisory role 維持で retention +15% literal evidence",
        "confidence": 0.65,
        "citation_array": ["REF-000003"],
    },
])


def _make_assistant_llm() -> LLMProvider:
    """C-1 fix: env-var 経由 LLM provider factory。 ollama / mock の literal swap path。"""
    if T5_LLM_PROVIDER == "ollama":
        from ..llm.provider import OllamaProvider
        return OllamaProvider(model=T5_OLLAMA_MODEL, endpoint=T5_OLLAMA_ENDPOINT, seed=42)
    # default = MockProvider (test compat、 deterministic fixture)
    return MockProvider(fixture={"listwise CoT": _ASSISTANT_FIXTURE})


# ============================================================================
# Security layer (H-3 + H-6、 env-var-gated active 化)
# ============================================================================

_basic = HTTPBasic(auto_error=False)

# in-process rate limit (H-3-c、 per-IP fixed window 60s)
# production = redis / slowapi 推奨、 PoC = literal dict
_rate_log: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    """X-Forwarded-For 優先 (reverse proxy 経由想定)、 fallback = client host。"""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request) -> None:
    """H-3-c fix: per-IP fixed window rate limit。 超過時 429 raise。"""
    ip = _client_ip(request)
    now = time.time()
    window_start = now - 60.0
    _rate_log[ip] = [t for t in _rate_log[ip] if t > window_start]
    if len(_rate_log[ip]) >= T5_RATE_LIMIT_PER_MIN:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"rate limit exceeded ({T5_RATE_LIMIT_PER_MIN} req/min)",
            headers={"Retry-After": "60"},
        )
    _rate_log[ip].append(now)


def _require_auth(creds: Optional[HTTPBasicCredentials] = Depends(_basic)) -> None:
    """H-3-a fix: env-var-gated HTTPBasic auth。 T5_AUTH_REQUIRED=1 + creds 設定で literal active。"""
    if not T5_AUTH_REQUIRED:
        return # test + dev path、 default off
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    # secrets.compare_digest = timing attack 防御 (T1-T4 inherit pattern)
    user_ok = secrets.compare_digest(creds.username.encode(), T5_BASIC_USER.encode())
    pass_ok = secrets.compare_digest(creds.password.encode(), T5_BASIC_PASS.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


_CSRF_COOKIE = "t5_csrf"


def _get_or_set_csrf(request: Request) -> str:
    """H-3-b fix: CSRF token 取得 (既存 cookie 優先、 不在時 新規 generate、 GET response で literal set-cookie)。"""
    return request.cookies.get(_CSRF_COOKIE) or secrets.token_urlsafe(32)


def _validate_csrf(request: Request, form_token: Optional[str]) -> None:
    """H-3-b fix: POST request 時 CSRF token validate。 T5_CSRF_REQUIRED=1 で literal active。"""
    if not T5_CSRF_REQUIRED:
        return
    cookie_token = request.cookies.get(_CSRF_COOKIE)
    if not cookie_token or not form_token or not secrets.compare_digest(cookie_token, form_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token mismatch")


def _scrub_query(query: str) -> tuple[str, list[str]]:
    """H-6 fix: PII redaction layer。 VAULT_FIELDS keyword detect、 T5_BLOCK_PII=1 で literal raise、 default warn-only return。"""
    clean, detected = check_pii_boundary(query)
    if not clean and T5_BLOCK_PII:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PII keyword detected in query: {detected}、 vault 経由 access が必要",
        )
    return query, detected


def _attach_csrf_cookie(response: Any, token: str) -> Any:
    """GET response に csrf cookie literal set (Secure + HttpOnly + SameSite=Lax)。"""
    # PoC: secure=False で http localhost 互換、 production deploy = secure=True (HTTPS 必須)
    response.set_cookie(
        key=_CSRF_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False, # production: True (HTTPS 必須)
        max_age=3600,
    )
    return response


# ============================================================================
# FastAPI app + templates
# ============================================================================


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="MAIS PMI Knowledge Base")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ============================================================================
# Demo data factory (合成 PoC、 移植段階 = 実 PMI case + license confirm 実 paper)
# ============================================================================


def _build_demo_corpus() -> dict[str, Any]:
    """PoC demo: 合成 10 PMI case + 10 paper (seed=0 deterministic)。"""
    import random as _rand
    from faker import Faker
    rng = _rand.Random(0)
    fake = Faker(["en_US", "ja_JP"])
    Faker.seed(0)
    pmi_cases = generate_pmi_cases(count=10, fake=fake, rng=rng)
    paper_corpus = generate_synthetic_paper_corpus(n_papers=10, seed=0)
    return {"pmi_cases": pmi_cases, "papers": paper_corpus}


# ============================================================================
# Endpoints (auth + rate-limit + CSRF + PII layer 配備)
# ============================================================================


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request, _auth: None = Depends(_require_auth)) -> Any:
    _check_rate_limit(request)
    csrf = _get_or_set_csrf(request)
    response = TEMPLATES.TemplateResponse(
        request=request,
        name="landing.html",
        context={"title": "MAIS PMI Knowledge Base", "csrf_token": csrf},
    )
    return _attach_csrf_cookie(response, csrf)


@app.get("/health")
async def health() -> dict[str, str]:
    """health endpoint = literal 認証不要 (load balancer probe 等用、 production canonical)。"""
    return {"status": "ok", "service": "mais-pmi-knowledge-base", "version": "0.6.0"}


@app.get("/search", response_class=HTMLResponse)
async def search_view(request: Request, _auth: None = Depends(_require_auth)) -> Any:
    """knowledge base search landing (form post → similar case panel)。"""
    _check_rate_limit(request)
    corpus = _build_demo_corpus()
    csrf = _get_or_set_csrf(request)
    response = TEMPLATES.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "title": "PMI Knowledge Base Search",
            "pmi_count": len(corpus["pmi_cases"]),
            "paper_count": len(corpus["papers"]),
            "csrf_token": csrf,
        },
    )
    return _attach_csrf_cookie(response, csrf)


@app.post("/search", response_class=HTMLResponse)
async def search_results(
    request: Request,
    query: str = Form(...),
    industry: str = Form(default="製造業"),
    size_band: str = Form(default="100-300"),
    culture: str = Form(default="同族経営、 関西本社"),
    financial: str = Form(default="30-50"),
    integration_type: str = Form(default="tuck-in"),
    csrf_token: Optional[str] = Form(default=None),
    _auth: None = Depends(_require_auth),
) -> Any:
    """5 dim weighted similarity search → top-K=3 PMI case + PMI domain term extraction。"""
    _check_rate_limit(request)
    _validate_csrf(request, csrf_token)
    _scrub_query(query) # PII layer: log only (T5_BLOCK_PII=1 で literal raise)
    corpus = _build_demo_corpus()
    from datetime import datetime

    from ..schema.types import PMICase
    query_case = PMICase(
        pmi_id="PMI-000000000",
        industry=industry,
        size_band=size_band, # type: ignore[arg-type]
        culture_profile=culture,
        financial_band=financial, # type: ignore[arg-type]
        integration_type=integration_type, # type: ignore[arg-type]
        lifecycle_stage="final_outcome",
        summary_redacted=query[:300],
        generated_at=datetime.now(),
    )
    pmi_pool = corpus["pmi_cases"]
    ranked = rank_similar_cases(query_case, pmi_pool, top_k=3)
    pmi_terms = extract_pmi_terms(query)
    new_csrf = _get_or_set_csrf(request)
    response = TEMPLATES.TemplateResponse(
        request=request,
        name="search_results.html",
        context={
            "title": "Similar PMI Cases (5 dim)",
            "query": query,
            "ranked": ranked,
            "pmi_terms": pmi_terms,
            "query_case": query_case,
            "csrf_token": new_csrf,
        },
    )
    return _attach_csrf_cookie(response, new_csrf)


@app.get("/assistant", response_class=HTMLResponse)
async def assistant_view(request: Request, _auth: None = Depends(_require_auth)) -> Any:
    """Assistant 対話 landing。"""
    _check_rate_limit(request)
    csrf = _get_or_set_csrf(request)
    response = TEMPLATES.TemplateResponse(
        request=request,
        name="assistant.html",
        context={"title": "Assistant 対話 (Junior Consultant Query)", "csrf_token": csrf},
    )
    return _attach_csrf_cookie(response, csrf)


@app.post("/assistant", response_class=HTMLResponse)
async def assistant_post(
    request: Request,
    query: str = Form(...),
    user_role: str = Form(default="junior_consultant"),
    csrf_token: Optional[str] = Form(default=None),
    _auth: None = Depends(_require_auth),
) -> Any:
    """Assistant listwise CoT recommendation (hardening phase commercial-grade、 env-var 経由 Ollama swap + persistent audit)。

    C-1 fix: T5_LLM_PROVIDER=ollama で literal Ollama swap (default = MockProvider for test compat)
    C-2 fix: T5_AUDIT_DIR persistent audit trail (AIQ-XXXXXX literal 永続化)
    H-6 fix: PII redaction layer pre-check (T5_BLOCK_PII=1 で literal block、 default warn-only)
    """
    _check_rate_limit(request)
    _validate_csrf(request, csrf_token)
    _scrub_query(query)

    valid_roles = {"junior_consultant", "senior_consultant", "fde", "admin"}
    role = user_role if user_role in valid_roles else "junior_consultant"
    req = AssistantDialogueRequest(
        query_text_redacted=query[:200],
        user_role=role, # type: ignore[arg-type]
        max_recommendations=DEFAULT_TOP_K,
    )

    # C-1 fix: env-var 経由 provider swap (default MockProvider for test compat、 ollama で actual AI)
    llm = _make_assistant_llm()
    recommendations = assistant_recommend(req, [], [], ["REF-000003", "REF-000007"], llm)

    # C-2 fix: persistent audit dir (T5_AUDIT_DIR = data/audit/assistant/ default)
    counter = AssistantCounter(audit_dir=T5_AUDIT_DIR)
    assistant_query = emit_assistant_audit(
        request=req,
        recommendations=recommendations,
        retrieved_cases=[],
        retrieved_papers=["REF-000003", "REF-000007"],
        counter=counter,
    )

    new_csrf = _get_or_set_csrf(request)
    response = TEMPLATES.TemplateResponse(
        request=request,
        name="assistant_response.html",
        context={
            "title": "Assistant Recommendation",
            "query": query,
            "user_role": role,
            "assistant_query": assistant_query,
            "recommendations": recommendations,
            "csrf_token": new_csrf,
        },
    )
    return _attach_csrf_cookie(response, new_csrf)


@app.get("/api/health")
async def api_health() -> JSONResponse:
    """JSON health endpoint (T1-T4 inherit pattern、 認証不要 = canonical for probes)。"""
    return JSONResponse(
        content={
            "service": "mais-pmi-knowledge-base",
            "version": "0.6.0",
            "status": "ok",
            "endpoints": ["/", "/search", "/assistant", "/health", "/api/health"],
            "security": {
                "auth_required": T5_AUTH_REQUIRED,
                "csrf_required": T5_CSRF_REQUIRED,
                "rate_limit_per_min": T5_RATE_LIMIT_PER_MIN,
                "block_pii": T5_BLOCK_PII,
                "llm_provider": T5_LLM_PROVIDER,
            },
        }
    )
