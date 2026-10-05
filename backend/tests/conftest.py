"""Tests must not depend on the developer's own .env (loaded when the server
module is imported): every test starts without an access token or a rate limit
setting, and sets what it needs itself."""

import pytest


@pytest.fixture(autouse=True)
def isolate_from_local_settings(monkeypatch):
    for name in ("BACKEND_ACCESS_TOKEN", "RATE_LIMIT_PER_MINUTE", "MODEL_EXTRA_BODY"):
        monkeypatch.delenv(name, raising=False)
