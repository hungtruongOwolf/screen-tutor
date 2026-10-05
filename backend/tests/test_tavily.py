"""Web lookups: the model asks for a search, the results come back, the answer cites them."""

import base64
import json

import httpx

from app.contract import CaptureMeta, ExplainTurnRequest
from app.explain import explain_turn
from app.openai_adapter import OpenAICompatibleAdapter
from app.tavily import Source, TavilySearch, describe_results
from fixtures import lecture_frame, to_png

CAPTURE = CaptureMeta(width=1280, height=720)

TAVILY_BODY = {
    "results": [
        {"title": "Pythagorean theorem - Wikipedia", "url": "https://en.wikipedia.org/wiki/Pythagorean_theorem", "content": "x" * 900},
        {"title": "Britannica", "url": "https://www.britannica.com/science/Pythagorean-theorem", "content": "History..."},
    ]
}


def tavily(status=200, body=None, error=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if error:
            raise error
        return httpx.Response(status, json=body if body is not None else TAVILY_BODY)

    return TavilySearch("tvly-test", transport=httpx.MockTransport(handler))


def request(question="Who proved this?"):
    return ExplainTurnRequest(
        session_id="s",
        question=question,
        image_base64=base64.b64encode(to_png(lecture_frame()[0])).decode(),
        capture=CAPTURE,
    )


def model(replies, seen, search):
    queue = list(replies)

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": queue.pop(0)}, "finish_reason": "stop"}]})

    return OpenAICompatibleAdapter(
        base_url="https://m.test/v1", api_key="k", model="m", search=search, transport=httpx.MockTransport(handler)
    )


ASK = json.dumps({"search": "who first proved the Pythagorean theorem"})
FINAL = json.dumps({"explanation": "According to Wikipedia, it is named after Pythagoras."})


def test_the_search_service_returns_titles_urls_and_trimmed_snippets():
    results = tavily()("anything")

    assert [r.title for r in results] == ["Pythagorean theorem - Wikipedia", "Britannica"]
    assert results[0].site == "en.wikipedia.org"
    assert len(results[0].snippet) <= 450


def test_a_failing_search_service_gives_no_results_not_an_error():
    assert tavily(status=500)("q") == []
    assert tavily(error=httpx.ConnectError("down"))("q") == []
    assert tavily(body={"unexpected": True})("q") == []


def test_the_model_asks_for_a_search_and_gets_the_results_before_answering():
    seen = []

    response = explain_turn(request(), adapter=model([ASK, FINAL], seen, tavily()))

    assert len(seen) == 2  # one call asked for the search, one gave the answer
    follow_up = seen[1]["messages"]
    assert follow_up[-1]["role"] == "user"
    assert "Wikipedia" in follow_up[-1]["content"] and "en.wikipedia.org" in follow_up[-1]["content"]
    assert follow_up[-2] == {"role": "assistant", "content": ASK}
    assert response.explanation.startswith("According to Wikipedia")
    assert response.trace.lookups == 1
    assert response.trace.attempts == 1  # the search was not a failed attempt
    assert [s.url for s in response.sources][0].startswith("https://en.wikipedia.org")


def test_a_turn_without_a_search_has_no_sources_and_one_model_call():
    seen = []

    response = explain_turn(request(), adapter=model([FINAL], seen, tavily()))

    assert len(seen) == 1 and response.sources == [] and response.trace.lookups == 0


def test_without_a_search_service_the_turn_still_completes():
    seen = []

    response = explain_turn(request(), adapter=model([ASK, FINAL], seen, None))

    assert "returned nothing" in seen[1]["messages"][-1]["content"]
    assert response.sources == [] and response.explanation


def test_the_model_is_only_allowed_one_search():
    seen = []
    asks_twice = [ASK, ASK, FINAL]

    response = explain_turn(request(), adapter=model(asks_twice, seen, tavily()))

    assert response.trace.lookups == 1
    assert response.trace.attempts == 2  # the second request counted as an unusable reply
    assert response.explanation


def test_the_prompt_tells_the_model_how_to_ask_for_a_search():
    from app.prompting import SYSTEM_PROMPT

    assert '{"search":' in SYSTEM_PROMPT


def test_the_results_message_for_nothing_found_says_so():
    assert "returned nothing" in describe_results("q", [])
    assert "1. T (x.com): s" in describe_results("q", [Source(title="T", url="https://x.com/a", snippet="s")])
