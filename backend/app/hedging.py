"""Hedged requests: when the first model is slow, ask a second one too.

The model service's speed varies a lot over time (the first step has taken from
about 3 to over 25 seconds for the same request). If the primary model has not
produced anything after `hedge_after` seconds, the same request goes to a second
model; whichever shows its first result first is used and the other is dropped.
Cost: a second request, only for the slow turns. If the primary fails outright
the second one is used straight away.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Iterator
from typing import Any

from .model_adapter import ModelAdapter

Event = tuple[str, Any]


class HedgedAdapter:
    def __init__(self, primary: ModelAdapter, secondary: ModelAdapter, hedge_after: float = 4.0) -> None:
        self.primary = primary
        self.secondary = secondary
        self.hedge_after = hedge_after
        self.name = primary.name

    def decide(self, **call: Any):
        final = None
        for kind, value in self.decide_events(**call):
            if kind == "final":
                final = value
        assert final is not None
        return final

    def decide_events(self, **call: Any) -> Iterator[Event]:
        events: queue.Queue[tuple[str, Event]] = queue.Queue()
        cancelled = {"primary": threading.Event(), "secondary": threading.Event()}
        adapters = {"primary": self.primary, "secondary": self.secondary}

        def pump(label: str) -> None:
            adapter = adapters[label]
            try:
                source = adapter.decide_events(**call) if hasattr(adapter, "decide_events") else _whole(adapter, call)
                for event in source:
                    if cancelled[label].is_set():
                        return  # the generator is dropped, which closes its connection
                    events.put((label, event))
                events.put((label, ("end", None)))
            except Exception as error:  # noqa: BLE001 - handed to the consumer
                events.put((label, ("error", error)))

        def start(label: str) -> None:
            threading.Thread(target=pump, args=(label,), daemon=True).start()

        start("primary")
        secondary_started = False
        deadline = time.monotonic() + self.hedge_after
        errors: dict[str, Exception] = {}
        winner: str | None = None

        while True:
            wait = None if secondary_started else max(0.0, deadline - time.monotonic())
            try:
                label, (kind, value) = events.get(timeout=wait)
            except queue.Empty:
                start("secondary")
                secondary_started = True
                continue

            if winner is None:
                if kind == "error":
                    errors[label] = value
                    if not secondary_started:
                        # The primary failed: do not wait for the clock.
                        start("secondary")
                        secondary_started = True
                    elif len(errors) == 2:
                        raise errors["primary"]
                    continue
                if kind == "end":
                    continue
                winner = label
                cancelled["secondary" if label == "primary" else "primary"].set()
            if label != winner:
                continue
            if kind == "error":
                raise value
            if kind == "end":
                return
            yield (kind, value)
            if kind == "final":
                return


def _whole(adapter: ModelAdapter, call: dict[str, Any]) -> Iterator[Event]:
    decision = adapter.decide(**call)
    from .model_adapter import StepDecision

    for step in decision.steps or [StepDecision(caption=decision.explanation, operations=decision.operations)]:
        yield ("step", step)
    yield ("final", decision)
