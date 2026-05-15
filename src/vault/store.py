"""T5 PII Vault: Fernet 暗号化 + audit log (T1-T4 inherit、 internal ADR § 3 + internal ADR § 4 PII/Op 分離 順守)。

試作 = Fernet (AES-128-CBC + HMAC-SHA256) で JSONL 暗号化、 移植 = KMS + envelope key 化 (doctrine: future-proof)。

T5 specific vault content:
- assistant_query_pii: raw_query_text + raw_user_name (AssistantQuery audit raw layer)
- decision_pii: raw_rationale (Decision rationale_redacted raw)
- outcome_pii: raw_retrospective + raw_owner_quote (Outcome retrospective raw)
- pmi_case_pii: client_company_name_real + deal_consideration_real (PMICase raw 企業名 + 取引金額)
- pattern_pii: raw_cross_case_evidence + raw_owner_name (Pattern cross-case evidence raw)
- paper_pii: paper_signatory + acknowledgments_raw (ReferencePaper raw 署名 + 謝辞)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

# Windows cp932 console UTF-8 reconfigure (T3 学び doctrine: analogical-recall inherit)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass


# ============================================================================
# Path resolution (env override path 確保、 doctrine: future-proof)
# ============================================================================


def _data_dir() -> Path:
    """env から DATA_DIR を lazy read (test 環境 + 移植段階 顧客 sandbox path override)。"""
    return Path(os.environ.get("DATA_DIR", "./data"))


def _vault_dir() -> Path:
    return _data_dir() / "vault"


def _audit_dir() -> Path:
    return _data_dir() / "audit"


def _audit_log_path() -> Path:
    return _audit_dir() / "vault_access_log.jsonl"


# ============================================================================
# Key management (試作 = env、 移植 = KMS + envelope key)
# ============================================================================


def generate_key() -> bytes:
    """Fernet key 生成 (test + .env 初期化用、 移植段階 = AWS KMS / Cloud KMS で literal 自動 rotation)。"""
    return Fernet.generate_key()


def _get_key() -> bytes:
    """VAULT_KEY env を取得 (試作)、 未設定なら RuntimeError + 生成 hint。

    移植段階 = KMS 経由 envelope key + per-record DEK (Data Encryption Key) literal 採用 path 確保。
    """
    key_str = os.environ.get("VAULT_KEY")
    if not key_str:
        key = generate_key()
        raise RuntimeError(
            "VAULT_KEY 未設定。 .env (or environment) に下記を literal 追記:\n"
            f"  VAULT_KEY={key.decode()}\n"
            "(試作用 Fernet key、 移植時は AWS KMS / Cloud KMS envelope key に置換、 doctrine: future-proof)"
        )
    return key_str.encode()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# Audit log (internal ADR layer 7 inherit + internal ADR § 4 PII layer separation 順守)
# ============================================================================


def emit_audit(
    action: str,
    item_id: str,
    vault_name: str,
    requester: str = "system",
    reason: str = "",
) -> None:
    """全 vault access を audit log に append (T1-T4 inherit、 ADR-007 layer 7 SSoT)。

    Args:
        action: "encrypt" / "decrypt" / "rotate" / "delete"
        item_id: vault item identifier (AIQ-XXXXXX / DEC-XXXXXX 等)
        vault_name: vault file name (assistant_query_pii / decision_pii 等)
        requester: caller identifier (system / user_role / api)
        reason: optional audit context (受託 deploy 段階の DPIA + GDPR Article 30 record)
    """
    _audit_dir().mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": _now_iso(),
        "action": action,
        "item_id": item_id,
        "vault_name": vault_name,
        "requester": requester,
        "reason": reason,
    }
    with _audit_log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ============================================================================
# Encrypt / Decrypt (Fernet 試作、 移植 = KMS envelope key)
# ============================================================================


def encrypt_to_vault(
    item_id: str,
    data: dict[str, Any],
    vault_name: str = "assistant_query_pii",
    requester: str = "system",
    reason: str = "",
) -> Path:
    """data dict を Fernet encrypt + vault file (.enc) に append。 audit log 同時 emit。

    T5 default vault_name = assistant_query_pii (AssistantQuery PII)、
    decision_pii / outcome_pii / pmi_case_pii / pattern_pii / paper_pii も同 pattern。

    Returns:
        vault file path (data/vault/{vault_name}.enc)
    """
    _vault_dir().mkdir(parents=True, exist_ok=True)
    cipher = Fernet(_get_key())
    vault_path = _vault_dir() / f"{vault_name}.enc"
    plaintext = json.dumps({"item_id": item_id, "data": data}, ensure_ascii=False).encode("utf-8")
    ciphertext = cipher.encrypt(plaintext)
    # append-only mode (受託 deploy 段階の immutable audit log 軸、 doctrine: client-no-recovery)
    with vault_path.open("ab") as f:
        f.write(ciphertext + b"\n")
    emit_audit("encrypt", item_id, vault_name, requester=requester, reason=reason)
    return vault_path


def decrypt_from_vault(
    item_id: str,
    vault_name: str = "assistant_query_pii",
    requester: str = "system",
    reason: str = "",
) -> dict[str, Any] | None:
    """vault file から item_id match 行 decrypt + 取得 (linear scan、 移植 = sqlite index pattern)。

    Returns:
        decrypted data dict、 未 match なら None。

    Raises:
        InvalidToken: VAULT_KEY 不一致 (key rotation 段階の literal error path)
    """
    vault_path = _vault_dir() / f"{vault_name}.enc"
    if not vault_path.exists():
        emit_audit("decrypt_miss", item_id, vault_name, requester=requester, reason="vault file not found")
        return None
    cipher = Fernet(_get_key())
    with vault_path.open("rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                plaintext = cipher.decrypt(line)
            except InvalidToken:
                # key rotation 段階の literal error path、 raise (silent skip 不採用 doctrine: no-design-compromise)
                raise
            record = json.loads(plaintext.decode("utf-8"))
            if record.get("item_id") == item_id:
                emit_audit("decrypt", item_id, vault_name, requester=requester, reason=reason)
                return record.get("data")  # type: ignore[no-any-return]
    emit_audit("decrypt_miss", item_id, vault_name, requester=requester, reason="item_id not found in vault")
    return None


__all__ = [
    "generate_key",
    "emit_audit",
    "encrypt_to_vault",
    "decrypt_from_vault",
]
