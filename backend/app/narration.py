"""Spoken narration: a step's on-screen caption rewritten as what a tutor would say out loud.

A caption is written to be read (symbols, short, packed with terms); said by a voice it sounds like a
list. An NVIDIA Nemotron model (through the same Nebius Token Factory API as the rest) rewrites it
as natural speech, in one or two short sentences, knowing what it said just before so the steps run
on from each other. It is quick (about 1 s: reasoning is switched off) and it runs while the step is
being drawn.

It never decides anything: if it fails, is slow, or its text drops a number from the caption, the
caption itself is read (the caller gets None and falls back).
"""

from __future__ import annotations

import re
import time
from typing import Protocol

import httpx

DEFAULT_NARRATION_MODEL = "nvidia/nemotron-3-super-120b-a12b"

SYSTEM = (
    "You are a friendly tutor speaking out loud while you point at things on the learner's screen. "
    "You will get the caption of one step. Say exactly what it says, in words that sound natural when spoken: "
    "formulas said in words (x squared, not x^2), no symbols or markup, one or two short sentences. Keep every "
    "number and every name or term of the caption. Never add, judge or conclude anything that is not in the "
    "caption: no new facts, no claims about what already exists or happened. If lines you said earlier are "
    "given, carry on from them and do not repeat them or greet again. Reply with only the words to say."
)


class Narrator(Protocol):
    name: str

    def narrate(self, caption: str, question: str, earlier: list[str]) -> str | None: ...


_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def spell(number: int) -> str:
    """0 to 999 in words ("thirty-six", "one hundred")."""
    if number < 20:
        return _ONES[number]
    if number < 100:
        tens, ones = divmod(number, 10)
        return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")
    hundreds, rest = divmod(number, 100)
    return f"{_ONES[hundreds]} hundred" + (f" {spell(rest)}" if rest else "")


def _numbers(text: str) -> list[str]:
    # An exponent (x^2, 6^{10}) is spoken as "squared" or "to the power": it is not a number to find.
    return re.findall(r"\d+(?:\.\d+)?", re.sub(r"\^\{?[+-]?\w+\}?", " ", text))


def _said(number: str, spoken: str) -> bool:
    """A number of the caption is in the speech as digits or, for a whole number, in words."""
    if number in re.findall(r"\d+(?:\.\d+)?", spoken):
        return True
    if number.isdigit() and int(number) < 1000:
        flat = re.sub(r"[-\s]+", " ", spoken.lower())
        return spell(int(number)).replace("-", " ") in flat
    return False


def acceptable(spoken: str, caption: str) -> bool:
    """The rewrite may be used only if it is plain speech of sensible length (one that runs on adds things
    the caption does not say) that still holds every number of the caption."""
    if not spoken or "\n" in spoken.strip() or len(spoken) > max(160, int(1.6 * len(caption))):
        return False
    if re.search(r"[`*#_|<>{}\[\]]", spoken):
        return False
    if len(re.findall(r"[.!?](?:\s|$)", spoken)) > 3:
        return False
    return all(_said(number, spoken) for number in _numbers(caption))


class NemotronNarrator:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = DEFAULT_NARRATION_MODEL,
        timeout: float = 6.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.name = model
        self._model = model
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def narrate(self, caption: str, question: str, earlier: list[str]) -> str | None:
        context = ""  # the question is deliberately not sent: it invites answers the caption does not give
        if earlier:
            context += "What you said just before:\n" + "\n".join(f"- {line}" for line in earlier[-3:]) + "\n"
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"{context}\nCaption of this step: {caption}"},
            ],
            "max_tokens": 200,
            "temperature": 0.3,
            "reasoning_effort": "none",  # without it the model thinks for seconds before the first word
        }
        try:
            response = self._client.post("/chat/completions", json=body)
            response.raise_for_status()
            spoken = (response.json()["choices"][0]["message"]["content"] or "").strip().strip('"')
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            return None
        return spoken if acceptable(spoken, caption) else None


def timed(narrator: Narrator, caption: str, question: str, earlier: list[str]) -> tuple[str | None, float]:
    started = time.perf_counter()
    spoken = narrator.narrate(caption, question, earlier)
    return spoken, (time.perf_counter() - started) * 1000
