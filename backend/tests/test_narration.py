"""Spoken narration: the caption said as a person would say it, never at the cost of a wrong number."""

import json

import httpx
from fastapi.testclient import TestClient

from app.narration import NemotronNarrator, acceptable
from app.server import create_app

CAPTION = "The legs are 6 and 8; the hypotenuse x is opposite the right angle."


def narrator_replying(content, status=200, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})

    return NemotronNarrator(base_url="http://model", api_key="k", transport=httpx.MockTransport(handler))


def test_a_plain_rewrite_that_keeps_the_numbers_is_used():
    seen = []
    narrator = narrator_replying("The two sides that make the right angle are the legs, 6 and 8, and x is across from it.", seen=seen)

    spoken = narrator.narrate(CAPTION, "why?", ["Look at the triangle."])

    assert spoken and "6 and 8" in spoken
    body = seen[0]
    assert body["model"].startswith("nvidia/")
    assert body["reasoning_effort"] == "none"  # reasoning off: otherwise the first word takes seconds
    prompt = body["messages"][1]["content"]
    assert "Look at the triangle." in prompt and CAPTION in prompt
    assert "why?" not in prompt  # the question would invite conclusions the caption does not draw


def test_a_rewrite_that_loses_a_number_or_is_not_plain_speech_is_refused():
    assert acceptable("The legs are six and eight.", CAPTION)  # spelled out is fine
    assert acceptable("Squared, thirty-six plus sixty-four makes one hundred.", "x^2 = 6^2 + 8^2 = 36 + 64 = 100".replace("6^2 + 8^2 = ", ""))
    assert acceptable("x squared is six squared plus eight squared.", "x^2 = 6^2 + 8^2")  # exponents are not numbers to find
    assert not acceptable("One. Two. Three. Four sentences now.", "Count 1 2 3 4")  # runs on
    assert not acceptable("The legs are 6 and 9.", CAPTION)
    assert not acceptable("**The legs** are 6 and 8.", CAPTION)
    assert not acceptable("", CAPTION)
    assert not acceptable("The legs are 6 and 8.\nSecond line.", CAPTION)
    assert acceptable("Both legs, 6 and 8, meet at the right angle.", CAPTION)


def test_a_failing_model_gives_none():
    assert narrator_replying("x", status=500).narrate(CAPTION, "", []) is None


def test_the_endpoint_falls_back_to_the_caption_when_there_is_no_narrator_or_it_fails(monkeypatch):
    monkeypatch.setenv("MODEL_ADAPTER", "fake")  # no real model, whatever the developer's .env says
    plain = TestClient(create_app())
    answer = plain.post("/narrate", json={"caption": CAPTION}).json()
    assert answer == {"spoken": CAPTION, "source": "caption", "model": ""}

    failing = TestClient(create_app(narrator=narrator_replying("x", status=500)))
    assert failing.post("/narrate", json={"caption": CAPTION}).json()["source"] == "caption"


def test_the_endpoint_returns_the_rewrite_and_says_which_model_made_it():
    good = TestClient(create_app(narrator=narrator_replying("Both legs, 6 and 8, meet at the right angle.")))

    answer = good.post("/narrate", json={"caption": CAPTION, "question": "q", "earlier": ["a"]}).json()

    assert answer["spoken"].startswith("Both legs")
    assert answer["source"] == "nemotron"
    assert answer["model"].startswith("nvidia/")


def test_the_endpoint_needs_the_access_token_and_health_lists_the_feature(monkeypatch):
    monkeypatch.setenv("MODEL_ADAPTER", "fake")
    monkeypatch.setenv("BACKEND_ACCESS_TOKEN", "secret")
    client = TestClient(create_app())

    assert client.post("/narrate", json={"caption": CAPTION}).status_code == 401
    ok = client.post("/narrate", json={"caption": CAPTION}, headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200
    assert "narration" in client.get("/health").json()["features"]
