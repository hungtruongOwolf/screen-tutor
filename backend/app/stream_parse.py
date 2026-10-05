"""Reads the steps of a model's JSON answer while the text is still arriving.

The model writes {"analysis": ..., "steps": [ {...}, {...} ], ...}. Fed the text
in whatever pieces it comes in, the parser returns each step object as soon as
its closing brace has arrived, so the first step can be drawn while the model is
still writing the second.
"""

from __future__ import annotations

import json
import re

_STEPS_KEY = re.compile(r'"steps"\s*:\s*\[')


class StepStreamParser:
    def __init__(self) -> None:
        self._buffer = ""
        self._position = 0
        self._inside_array = False
        self._depth = 0  # 0 = between steps (inside the array), 1+ = inside a step
        self._in_string = False
        self._escaped = False
        self._start: int | None = None
        self.finished = False  # the steps array has been closed

    def feed(self, text: str) -> list[dict]:
        """Add text; return the step objects completed by it (as dicts)."""
        self._buffer += text
        found: list[dict] = []
        if self.finished:
            return found
        if not self._inside_array:
            match = _STEPS_KEY.search(self._buffer)
            if not match:
                return found
            self._inside_array = True
            self._position = match.end()

        buffer = self._buffer
        index = self._position
        while index < len(buffer):
            char = buffer[index]
            if self._in_string:
                if self._escaped:
                    self._escaped = False
                elif char == "\\":
                    self._escaped = True
                elif char == '"':
                    self._in_string = False
            elif char == '"':
                self._in_string = True
            elif char in "{[":
                if self._depth == 0 and char == "{":
                    self._start = index
                self._depth += 1
            elif char in "}]":
                if self._depth == 0:
                    # The "]" that closes the steps array.
                    self.finished = True
                    index += 1
                    break
                self._depth -= 1
                if self._depth == 0 and char == "}" and self._start is not None:
                    try:
                        found.append(json.loads(buffer[self._start : index + 1]))
                    except ValueError:
                        pass  # a malformed step is caught when the whole answer is parsed
                    self._start = None
            index += 1
        self._position = index
        return found
