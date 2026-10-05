"""Steps are read from the model's JSON while it is still being written."""

import json

from app.stream_parse import StepStreamParser

ANSWER = {
    "analysis": 'a "steps": [ in a string } ] ',
    "explanation": "sum",
    "steps": [
        {"caption": "one {with} braces and \"quotes\"", "shapes": [{"kind": "box", "region_id": 3}]},
        {"caption": "two", "shapes": [{"kind": "equation", "region_id": 0, "text": "a^2 + b^2 = c^2"}], "remove": ["x"]},
        {"caption": "three", "shapes": []},
    ],
    "region_ids": [3],
}


def feed_in_pieces(text: str, size: int) -> list[dict]:
    parser = StepStreamParser()
    steps = []
    for start in range(0, len(text), size):
        steps += parser.feed(text[start : start + size])
    return steps


def test_all_steps_come_out_whatever_the_size_of_the_pieces():
    text = json.dumps(ANSWER)

    for size in (1, 2, 5, 17, 64, len(text)):
        assert feed_in_pieces(text, size) == ANSWER["steps"], size


def test_a_step_is_returned_as_soon_as_it_is_complete_not_before():
    text = json.dumps(ANSWER)
    parser = StepStreamParser()
    cut = text.index('"caption": "two"')  # inside the second step

    first = parser.feed(text[:cut])
    rest = parser.feed(text[cut:])

    assert [s["caption"] for s in first] == ['one {with} braces and "quotes"']
    assert [s["caption"] for s in rest] == ["two", "three"]


def test_braces_and_brackets_inside_strings_do_not_confuse_it():
    text = json.dumps({"steps": [{"caption": "} ] { [ \" \ "}]})

    assert feed_in_pieces(text, 3) == [{"caption": '} ] { [ " \ '}]


def test_an_answer_without_steps_gives_nothing():
    assert feed_in_pieces(json.dumps({"explanation": "x", "shapes": []}), 4) == []


def test_it_stops_at_the_end_of_the_steps_array():
    parser = StepStreamParser()
    parser.feed('{"steps": [{"caption": "a"}], "later": [{"caption": "not a step"}]}')

    assert parser.finished
    assert parser.feed('{"caption": "more"}') == []


def test_a_broken_step_is_skipped_and_the_next_one_still_comes():
    text = '{"steps": [{"caption": nope}, {"caption": "ok"}]}'

    assert feed_in_pieces(text, 5) == [{"caption": "ok"}]
