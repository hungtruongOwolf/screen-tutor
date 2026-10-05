import base64
import json

from fastapi.testclient import TestClient

from app.contract import CaptureMeta, ExplainTurnRequest
from app.model_adapter import RecordedModelAdapter
from app.ratelimit import SlidingWindowLimiter
from app.server import create_app
from fixtures import lecture_frame, to_png


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_the_limit_applies_per_key_within_the_window():
    clock = Clock()
    limiter = SlidingWindowLimiter(2, 60, clock)

    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")  # another caller has its own count


def test_the_window_slides():
    clock = Clock()
    limiter = SlidingWindowLimiter(1, 60, clock)

    assert limiter.allow("a")
    clock.now = 30
    assert not limiter.allow("a")
    clock.now = 61
    assert limiter.allow("a")


def test_the_endpoint_answers_429_when_a_caller_goes_over_the_limit(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    client = TestClient(create_app(RecordedModelAdapter()))
    payload = ExplainTurnRequest(
        session_id="s", question="q",
        image_base64=base64.b64encode(to_png(lecture_frame()[0])).decode(),
        capture=CaptureMeta(width=1280, height=720),
    ).model_dump()

    codes = [client.post("/explain-turn", json=payload).status_code for _ in range(4)]

    assert codes == [200, 200, 429, 429]
