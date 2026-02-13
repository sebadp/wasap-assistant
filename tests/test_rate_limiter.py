import time
from unittest.mock import patch

from app.webhook.rate_limiter import RateLimiter


def test_allows_within_limit():
    rl = RateLimiter(max_requests=3, window_seconds=60)
    assert rl.is_allowed("user1") is True
    assert rl.is_allowed("user1") is True
    assert rl.is_allowed("user1") is True


def test_blocks_over_limit():
    rl = RateLimiter(max_requests=2, window_seconds=60)
    assert rl.is_allowed("user1") is True
    assert rl.is_allowed("user1") is True
    assert rl.is_allowed("user1") is False


def test_separate_keys():
    rl = RateLimiter(max_requests=1, window_seconds=60)
    assert rl.is_allowed("user1") is True
    assert rl.is_allowed("user2") is True
    assert rl.is_allowed("user1") is False
    assert rl.is_allowed("user2") is False


def test_window_expiry():
    rl = RateLimiter(max_requests=1, window_seconds=1)
    assert rl.is_allowed("user1") is True
    assert rl.is_allowed("user1") is False

    # Simulate time passing beyond the window
    with patch("time.monotonic", return_value=time.monotonic() + 2):
        assert rl.is_allowed("user1") is True
