"""tests for src/vault/ (Week 4 sub-task 2、 Fernet 暗号化、 11 test)"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.vault.store import (
    decrypt_from_vault,
    emit_audit,
    encrypt_to_vault,
    generate_key,
)


# === generate_key ===


def test_generate_key_44_bytes():
    """Fernet key = 44 byte URL-safe base64。"""
    key = generate_key()
    assert isinstance(key, bytes)
    assert len(key) == 44


def test_generate_key_unique():
    """毎回 unique key (literal random 性)。"""
    k1 = generate_key()
    k2 = generate_key()
    assert k1 != k2


# === encrypt + decrypt round-trip ===


@pytest.fixture
def vault_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VAULT_KEY", generate_key().decode())
    return tmp_path


def test_encrypt_creates_vault_file(vault_env: Path):
    data = {"raw_query_text": "機密内容", "raw_user_name": "(author)太郎"}
    p = encrypt_to_vault("LIL-000001", data, vault_name="assistant_query_pii")
    assert p.exists()
    assert p.name == "assistant_query_pii.enc"


def test_decrypt_round_trip(vault_env: Path):
    data = {"raw_query_text": "Day-1 機密 query", "raw_user_name": "テスト太郎"}
    encrypt_to_vault("LIL-000001", data, vault_name="assistant_query_pii")
    decrypted = decrypt_from_vault("LIL-000001", vault_name="assistant_query_pii")
    assert decrypted == data


def test_decrypt_missing_item_none(vault_env: Path):
    encrypt_to_vault("LIL-000001", {"x": "y"}, vault_name="assistant_query_pii")
    missing = decrypt_from_vault("LIL-999999", vault_name="assistant_query_pii")
    assert missing is None


def test_decrypt_nonexistent_vault_returns_none(vault_env: Path):
    """vault file 不在 = silent None return (audit emit + early short-circuit)。"""
    missing = decrypt_from_vault("LIL-x", vault_name="nonexistent_vault")
    assert missing is None


def test_multi_item_selective_decrypt(vault_env: Path):
    encrypt_to_vault("LIL-000001", {"v": "1"}, vault_name="assistant_query_pii")
    encrypt_to_vault("LIL-000002", {"v": "2"}, vault_name="assistant_query_pii")
    encrypt_to_vault("LIL-000003", {"v": "3"}, vault_name="assistant_query_pii")
    target = decrypt_from_vault("LIL-000002", vault_name="assistant_query_pii")
    assert target == {"v": "2"}


# === audit log emit ===


def test_audit_log_emitted_on_encrypt(vault_env: Path):
    encrypt_to_vault("LIL-000001", {"x": "y"}, vault_name="assistant_query_pii", requester="test", reason="smoke")
    audit_path = vault_env / "audit" / "vault_access_log.jsonl"
    assert audit_path.exists()
    lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
    record = json.loads(lines[-1])
    assert record["action"] == "encrypt"
    assert record["item_id"] == "LIL-000001"
    assert record["vault_name"] == "assistant_query_pii"
    assert record["requester"] == "test"


def test_audit_log_emitted_on_decrypt(vault_env: Path):
    encrypt_to_vault("LIL-000001", {"x": "y"}, vault_name="assistant_query_pii")
    decrypt_from_vault("LIL-000001", vault_name="assistant_query_pii", requester="test", reason="verify")
    audit_path = vault_env / "audit" / "vault_access_log.jsonl"
    lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
    actions = [json.loads(l)["action"] for l in lines]
    assert "encrypt" in actions
    assert "decrypt" in actions


def test_audit_log_decrypt_miss(vault_env: Path):
    """item_id missing access も literal audit (access pattern attack 検出)。"""
    encrypt_to_vault("LIL-000001", {"x": "y"}, vault_name="assistant_query_pii")
    decrypt_from_vault("LIL-999999", vault_name="assistant_query_pii")
    audit_path = vault_env / "audit" / "vault_access_log.jsonl"
    actions = [json.loads(l)["action"] for l in audit_path.read_text(encoding="utf-8").strip().split("\n")]
    assert "decrypt_miss" in actions


# === missing VAULT_KEY fail-loud ===


def test_encrypt_no_key_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("VAULT_KEY", raising=False)
    with pytest.raises(RuntimeError, match="VAULT_KEY"):
        encrypt_to_vault("LIL-000001", {"x": "y"}, vault_name="assistant_query_pii")
