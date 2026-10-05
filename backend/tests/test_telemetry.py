"""Logs and metrics: useful numbers, and nothing about the content of a turn."""

import base64
import json

import cv2
from fastapi.testclient import TestClient

from app.contract import CaptureMeta, ExplainTurnRequest
from app.explain import explain_turn
from app.model_adapter import RecordedModelAdapter
from app.server import create_app
from fixtures import lecture_frame, to_png

CAPTURE = CaptureMeta(width=1280, height=720)
SECRET_QUESTION = "what is the secret in my private document?"


def payload(image_bytes: bytes) -> dict:
    return ExplainTurnRequest(
        session_id="s",
        question=SECRET_QUESTION,
        image_base64=base64.b64encode(image_bytes).decode(),
        capture=CAPTURE,
    ).model_dump()


def metric_lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.splitlines() if line.startswith("{") and "_aws" in line]


def test_a_turn_writes_one_metric_line_with_latency_and_counts(capsys):
    client = TestClient(create_app(RecordedModelAdapter()))

    response = client.post("/explain-turn", json=payload(to_png(lecture_frame()[0])))

    assert response.status_code == 200
    [line] = metric_lines(capsys.readouterr().out)
    declared = {m["Name"] for m in line["_aws"]["CloudWatchMetrics"][0]["Metrics"]}
    assert {"TurnLatencyMs", "ModelLatencyMs", "RegionsLatencyMs", "Attempts", "Steps", "TurnFailures"} <= declared
    assert line["Model"] == "recorded" and line["Status"] == 200 and line["TurnFailures"] == 0
    assert line["TurnLatencyMs"] > 0


def test_nothing_about_the_content_is_logged(capsys):
    client = TestClient(create_app(RecordedModelAdapter()))

    client.post("/explain-turn", json=payload(to_png(lecture_frame()[0])))

    out = capsys.readouterr().out
    assert SECRET_QUESTION not in out
    assert "image" not in out.lower().replace("imagenet", "")  # no image data or field
    assert "canned answer" not in out  # nor the answer


def test_a_failed_turn_is_counted_as_a_failure(capsys):
    client = TestClient(create_app(RecordedModelAdapter()))
    bad = payload(b"not an image")

    response = client.post("/explain-turn", json=bad)

    assert response.status_code == 400
    [line] = metric_lines(capsys.readouterr().out)
    assert line["TurnFailures"] == 1 and line["Status"] == 400


def test_a_jpeg_capture_is_accepted():
    ok, jpeg = cv2.imencode(".jpg", lecture_frame()[0], [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    request = ExplainTurnRequest(
        session_id="s", question="q", image_base64=base64.b64encode(jpeg.tobytes()).decode(), capture=CAPTURE
    )

    response = explain_turn(request, adapter=RecordedModelAdapter())

    assert any(r.kind == "figure" for r in response.regions)
