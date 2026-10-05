"""Web lookup with Tavily.

The model can ask for a search when the learner's question needs a fact, a
definition or a source that is not on the screen. The results are given back to
the model, which cites them. A failed lookup never fails the turn.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

SEARCH_URL = "https://api.tavily.com/search"
MAX_RESULTS = 3
SNIPPET_CHARS = 450


class Source(BaseModel):
    title: str
    url: str
    snippet: str = ""

    @property
    def site(self) -> str:
        host = urlparse(self.url).netloc
        return host.removeprefix("www.") or self.url


class TavilySearch:
    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 12.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout, transport=transport
        )

    def __call__(self, query: str) -> list[Source]:
        """The top results for the query, or an empty list if the service fails."""
        try:
            response = self._client.post(
                SEARCH_URL,
                json={"query": query, "max_results": MAX_RESULTS, "search_depth": "basic"},
            )
            if response.status_code != 200:
                return []
            results = response.json().get("results", [])
        except (httpx.HTTPError, ValueError):
            return []
        sources = []
        for item in results[:MAX_RESULTS]:
            title, url = item.get("title"), item.get("url")
            if title and url:
                sources.append(
                    Source(title=title, url=url, snippet=(item.get("content") or "")[:SNIPPET_CHARS])
                )
        return sources


def describe_results(query: str, sources: list[Source]) -> str:
    """The message that hands the results back to the model."""
    if not sources:
        return (
            f'The web search for "{query}" returned nothing. Answer from what you know, '
            "say that you could not check a source, and reply with the final JSON (no search)."
        )
    lines = [f'Web search results for "{query}":']
    for number, source in enumerate(sources, start=1):
        lines.append(f"{number}. {source.title} ({source.site}): {source.snippet}")
    lines.append(
        "Now answer using these results. Name the source (its site or title) in the explanation "
        "or in a caption, for example 'according to Britannica'. Reply with the final JSON (no search)."
    )
    return "\n".join(lines)
