"""The public web playground: the page, its files and the guarded open endpoint."""

import base64

from fastapi.testclient import TestClient

from app.contract import CaptureMeta, ExplainTurnRequest
from app.model_adapter import RecordedModelAdapter
from app.playground import MAX_IMAGE_CHARS, STATIC
from app.server import create_app
from fixtures import lecture_frame, to_png


def payload(**changes) -> dict:
    body = ExplainTurnRequest(
        session_id="s",
        question="What is this?",
        image_base64=base64.b64encode(to_png(lecture_frame()[0])).decode(),
        capture=CaptureMeta(width=1280, height=720),
    ).model_dump()
    body.update(changes)
    return body


def client() -> TestClient:
    return TestClient(create_app(RecordedModelAdapter()))


def test_the_page_and_its_files_are_served():
    c = client()

    page = c.get("/")
    assert page.status_code == 200 and "Sherpa playground" in page.text
    assert "/static/render.js" in page.text
    assert c.get("/static/render.js").status_code == 200
    for sample in ("triangle", "toolbar", "bullets"):
        assert c.get(f"/static/samples/{sample}.png").status_code == 200


def test_the_bundled_renderer_exposes_what_the_page_calls():
    script = (STATIC / "render.js").read_text(encoding="utf-8")

    assert "SherpaRender" in script
    assert "renderCanvasSvg" in script and "renderRegionsDebugSvg" in script


def test_the_open_endpoint_needs_no_token_even_when_the_app_endpoint_does(monkeypatch):
    monkeypatch.setenv("BACKEND_ACCESS_TOKEN", "secret")
    c = client()

    assert c.post("/explain-turn", json=payload()).status_code == 401
    open_call = c.post("/playground/explain", json=payload())

    assert open_call.status_code == 200
    assert open_call.json()["steps"]


def test_a_picture_that_is_too_large_is_refused():
    response = client().post("/playground/explain", json=payload(image_base64="A" * (MAX_IMAGE_CHARS + 1)))

    assert response.status_code == 413


def test_a_very_long_question_is_refused():
    assert client().post("/playground/explain", json=payload(question="x" * 301)).status_code == 400


def test_too_many_requests_from_one_visitor_get_429(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_RATE_PER_MINUTE", "2")
    c = client()

    codes = [c.post("/playground/explain", json=payload(), headers={"x-forwarded-for": "9.9.9.9"}).status_code for _ in range(3)]
    other = c.post("/playground/explain", json=payload(), headers={"x-forwarded-for": "8.8.8.8"}).status_code

    assert codes == [200, 200, 429]
    assert other == 200  # a different visitor has their own allowance


def test_it_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_ENABLED", "0")
    c = client()

    assert c.get("/").status_code == 404
    assert c.post("/playground/explain", json=payload()).status_code == 404
    assert c.get("/health").status_code == 200  # the rest still works


def test_health_says_which_features_this_version_has():
    from app.server import FEATURES

    c = TestClient(create_app())

    body = c.get("/health").json()

    assert body["status"] == "ok"
    assert {"history", "tasks", "stream"} <= set(body["features"]) == set(FEATURES)

