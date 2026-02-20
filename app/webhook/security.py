import hashlib
import hmac


def validate_signature(payload: bytes, signature_header: str, app_secret: str) -> bool:
    """Validate the X-Hub-Signature-256 header from Meta webhooks."""
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), payload, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)
