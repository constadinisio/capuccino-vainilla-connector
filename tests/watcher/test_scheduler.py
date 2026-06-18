"""Tests del loop del watcher."""
from __future__ import annotations

from capuccino_vainilla.watcher.scheduler import Scheduler


def test_runs_until_should_stop_and_sleeps_between_ticks():
    state = {"ticks": 0}
    slept: list[float] = []

    def tick():
        state["ticks"] += 1

    Scheduler(
        tick, interval=5, sleep=slept.append, should_stop=lambda: state["ticks"] >= 3
    ).run_forever()

    assert state["ticks"] == 3
    assert slept == [5, 5]  # duerme entre ticks, no tras el último


def test_survives_failing_tick():
    state = {"ticks": 0}

    def tick():
        state["ticks"] += 1
        if state["ticks"] == 1:
            raise RuntimeError("boom")

    Scheduler(
        tick, interval=1, sleep=lambda s: None, should_stop=lambda: state["ticks"] >= 2
    ).run_forever()

    assert state["ticks"] == 2  # siguió tras la excepción
