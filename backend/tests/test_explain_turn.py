"""Seam 1: Explain Turn. Tests call the turn interface with a recorded model."""

import base64
import struct
import zlib

import pytest
from fastapi.testclient import TestClient

from app.contract import (
    Anchor,
    Canvas,
    CaptureMeta,
    ExplainTurnRequest,
    ExplainTurnResponse,
    Operation,
    Shape,
)
from app.explain import BadRequest, explain_turn
from app.model_adapter import ModelDecision, RecordedModelAdapter
from app.server import create_app


def make_png(width: int = 8, height: int = 6) -> bytes:
    """A tiny valid PNG, built by hand so tests need no imaging library."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def make_request(canvas: Canvas | None = None, turn: int = 0) -> ExplainTurnRequest:
    return ExplainTurnRequest(
        session_id="test-session",
        question="What is this?",
        image_base64=base64.b64encode(make_png()).decode(),
        capture=CaptureMeta(width=800, height=600),
        canvas=canvas or Canvas(),
        turn=turn,
    )


def box(shape_id: str, region_id: int = 0) -> Shape:
    return Shape(
        id=shape_id,
        kind="box",
        anchor=Anchor(region_id=region_id, x=0.1, y=0.1, w=0.5, h=0.5),
    )


def test_response_matches_the_contract():
    response = explain_turn(make_request(), adapter=RecordedModelAdapter())

    ExplainTurnResponse.model_validate(response.model_dump())
    assert response.explanation
    assert response.trace.model == "recorded"
    assert response.trace.regions_proposed == len(response.regions)
    assert sum(response.trace.region_counts.values()) == len(response.regions)
    assert response.trace.timings_ms["total"] >= 0


def test_every_shape_anchors_to_a_region_that_exists_and_is_in_bounds():
    response = explain_turn(make_request(), adapter=RecordedModelAdapter())

    regions = {region.id: region for region in response.regions}
    assert response.canvas.shapes
    for shape in response.canvas.shapes:
        region = regions[shape.anchor.region_id]
        assert region.bbox.x >= 0 and region.bbox.y >= 0
        assert region.bbox.x + region.bbox.w <= 800
        assert region.bbox.y + region.bbox.h <= 600
        anchor = shape.anchor
        assert anchor.x + anchor.w <= 1 and anchor.y + anchor.h <= 1


def test_existing_shapes_are_kept_and_new_ones_added():
    existing = Canvas(shapes=[box("old")])

    response = explain_turn(make_request(existing, turn=1), adapter=RecordedModelAdapter())

    assert [shape.id for shape in response.canvas.shapes] == ["old", "turn1-box"]


def test_operations_can_update_and_remove_by_id():
    existing = Canvas(shapes=[box("a"), box("b")])
    decision = ModelDecision(
        explanation="edit",
        chosen_region_ids=[0],
        operations=[
            Operation(op="remove", shape_id="a"),
            Operation(op="update", shape_id="b", shape=box("b").model_copy(update={"text": "new"})),
        ],
    )

    response = explain_turn(make_request(existing), adapter=RecordedModelAdapter(decision))

    assert [shape.id for shape in response.canvas.shapes] == ["b"]
    assert response.canvas.shapes[0].text == "new"


def test_shape_anchored_to_unknown_region_is_rejected():
    decision = ModelDecision(
        explanation="bad",
        operations=[Operation(op="add", shape_id="x", shape=box("x", region_id=99))],
    )

    with pytest.raises(BadRequest):
        explain_turn(make_request(), adapter=RecordedModelAdapter(decision))


@pytest.mark.parametrize("image", ["not base64 !!", base64.b64encode(b"not a png").decode()])
def test_bad_image_is_rejected(image):
    request = make_request().model_copy(update={"image_base64": image})

    with pytest.raises(BadRequest):
        explain_turn(request, adapter=RecordedModelAdapter())


def test_http_endpoint_serves_the_same_turn():
    client = TestClient(create_app(RecordedModelAdapter()))

    response = client.post("/explain-turn", json=make_request().model_dump())

    assert response.status_code == 200
    ExplainTurnResponse.model_validate(response.json())


def test_http_endpoint_rejects_a_bad_image_with_400():
    client = TestClient(create_app(RecordedModelAdapter()))
    payload = make_request().model_dump()
    payload["image_base64"] = base64.b64encode(b"not a png").decode()

    assert client.post("/explain-turn", json=payload).status_code == 400


def test_access_token_is_enforced_when_configured(monkeypatch):
    monkeypatch.setenv("BACKEND_ACCESS_TOKEN", "secret")
    client = TestClient(create_app(RecordedModelAdapter()))
    payload = make_request().model_dump()

    assert client.post("/explain-turn", json=payload).status_code == 401
    ok = client.post(
        "/explain-turn", json=payload, headers={"Authorization": "Bearer secret"}
    )
    assert ok.status_code == 200
