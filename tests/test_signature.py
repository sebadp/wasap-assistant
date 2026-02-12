import hashlib
import hmac

from app.webhook.security import validate_signature


def test_valid_signature():
    payload = b'{"test": "data"}'
    secret = "my_secret"
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert validate_signature(payload, f"sha256={sig}", secret) is True


def test_invalid_signature():
    payload = b'{"test": "data"}'
    assert validate_signature(payload, "sha256=bad", "my_secret") is False


def test_missing_prefix():
    payload = b'{"test": "data"}'
    assert validate_signature(payload, "invalid_header", "my_secret") is False


def test_empty_signature():
    payload = b'{"test": "data"}'
    assert validate_signature(payload, "", "my_secret") is False
