import jwt
import pytest
from jwt import InvalidTokenError

from app.config import settings
from app.jwt_keys import decode_jwt, encode_jwt


def test_tokens_are_issued_with_active_key_id_and_decode_with_current_key(monkeypatch):
    monkeypatch.setattr(settings, "jwt_key_id", "key-2026-02")
    monkeypatch.setattr(settings, "jwt_secret", "current-secret-" + "c" * 64)
    monkeypatch.setattr(settings, "jwt_previous_secret", None)
    token = encode_jwt({"sub": "founder@example.test"})
    assert jwt.get_unverified_header(token)["kid"] == "key-2026-02"
    assert decode_jwt(token)["sub"] == "founder@example.test"


def test_previous_key_remains_valid_during_rotation_window(monkeypatch):
    old_secret = "old-secret-" + "o" * 64
    new_secret = "new-secret-" + "n" * 64
    old_token = jwt.encode({"sub": "founder@example.test"}, old_secret, algorithm="HS256", headers={"kid": "key-old"})
    monkeypatch.setattr(settings, "jwt_key_id", "key-new")
    monkeypatch.setattr(settings, "jwt_secret", new_secret)
    monkeypatch.setattr(settings, "jwt_previous_key_id", "key-old")
    monkeypatch.setattr(settings, "jwt_previous_secret", old_secret)
    assert decode_jwt(old_token)["sub"] == "founder@example.test"
    new_token = encode_jwt({"sub": "founder@example.test"})
    assert jwt.get_unverified_header(new_token)["kid"] == "key-new"
    assert decode_jwt(new_token)["sub"] == "founder@example.test"


def test_legacy_token_without_kid_uses_previous_key_during_rotation(monkeypatch):
    old_secret = "old-secret-" + "o" * 64
    token = jwt.encode({"sub": "legacy@example.test"}, old_secret, algorithm="HS256")
    monkeypatch.setattr(settings, "jwt_key_id", "key-new")
    monkeypatch.setattr(settings, "jwt_secret", "new-secret-" + "n" * 64)
    monkeypatch.setattr(settings, "jwt_previous_key_id", "key-old")
    monkeypatch.setattr(settings, "jwt_previous_secret", old_secret)
    assert decode_jwt(token)["sub"] == "legacy@example.test"


def test_unknown_key_id_is_rejected(monkeypatch):
    token = jwt.encode({"sub": "x"}, "untrusted-secret-" + "u" * 64, algorithm="HS256", headers={"kid": "unknown"})
    monkeypatch.setattr(settings, "jwt_key_id", "key-current")
    monkeypatch.setattr(settings, "jwt_secret", "current-secret-" + "c" * 64)
    monkeypatch.setattr(settings, "jwt_previous_secret", None)
    with pytest.raises(InvalidTokenError, match="Unknown JWT signing key"):
        decode_jwt(token)
