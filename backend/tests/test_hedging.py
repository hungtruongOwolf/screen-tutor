"""Hedged requests: the second model is only asked when the first is slow or fails."""

import threading
import time

import pytest

from app.hedging import HedgedAdapter
from app.model_adapter import ModelDecision, StepDecision


class Fake:
    """Takes `delay` seconds before its first step, then gives two steps."""

    def __init__(self, name, delay=0.0, fail=False):
        self.name = name
        self.delay = delay
        self.fail = fail
        self.calls = 0
        self.finished = threading.Event()

    def decide_events(self, **call):
        self.calls += 1
        try:
            time.sleep(self.delay)
            if self.fail:
                raise RuntimeError(f"{self.name} broke")
            for index in range(2):
                yield ("step", StepDecision(caption=f"{self.name} {index}"))
            yield ("final", ModelDecision(explanation=self.name, model=self.name))
        finally:
            self.finished.set()


def run(adapter):
    return list(adapter.decide_events(question="q"))


def test_a_fast_primary_is_enough_and_the_second_is_never_asked():
    primary, secondary = Fake("fast", 0.0), Fake("backup", 0.0)

    events = run(HedgedAdapter(primary, secondary, hedge_after=0.3))

    assert [v.caption for k, v in events if k == "step"] == ["fast 0", "fast 1"]
    assert events[-1][1].model == "fast"
    assert secondary.calls == 0


def test_a_slow_primary_is_overtaken_by_the_second_model():
    primary, secondary = Fake("slow", 0.6), Fake("backup", 0.0)

    events = run(HedgedAdapter(primary, secondary, hedge_after=0.05))

    assert [v.caption for k, v in events if k == "step"] == ["backup 0", "backup 1"]  # never mixed
    assert events[-1][1].model == "backup"
    assert secondary.calls == 1


def test_a_primary_that_answers_just_after_the_clock_still_wins_if_it_is_first():
    primary, secondary = Fake("a", 0.15), Fake("b", 0.6)

    events = run(HedgedAdapter(primary, secondary, hedge_after=0.05))

    assert events[-1][1].model == "a"


def test_a_failing_primary_hands_over_at_once():
    primary, secondary = Fake("broken", 0.0, fail=True), Fake("backup", 0.0)
    started = time.monotonic()

    events = run(HedgedAdapter(primary, secondary, hedge_after=5.0))

    assert events[-1][1].model == "backup"
    assert time.monotonic() - started < 1.0  # did not wait for the 5 second clock


def test_if_both_fail_the_primary_error_is_raised():
    adapter = HedgedAdapter(Fake("one", fail=True), Fake("two", fail=True), hedge_after=0.05)

    with pytest.raises(RuntimeError, match="one broke"):
        run(adapter)


def test_the_loser_is_told_to_stop():
    primary, secondary = Fake("slow", 0.4), Fake("fast", 0.0)

    run(HedgedAdapter(primary, secondary, hedge_after=0.05))

    assert primary.finished.wait(timeout=3)  # the slow one's connection is released


def test_decide_gives_the_final_decision():
    decision = HedgedAdapter(Fake("p"), Fake("s"), hedge_after=1).decide(question="q")

    assert decision.model == "p"


def test_the_name_is_the_primary_s_for_logs():
    assert HedgedAdapter(Fake("p"), Fake("s")).name == "p"
