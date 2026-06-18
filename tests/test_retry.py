"""Tests del mecanismo de reintentos."""

from __future__ import annotations

import pytest

from capuccino_vainilla.retry import retry_call


class _Boom(Exception):
    pass


class _Other(Exception):
    pass


def test_returns_on_first_success():
    calls = []
    result = retry_call(lambda: "ok", description="op", sleep=calls.append)
    assert result == "ok"
    assert calls == []  # no hubo esperas


def test_retries_then_succeeds():
    attempts = {"n": 0}
    sleeps: list[float] = []

    def op():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _Boom("transient")
        return "done"

    result = retry_call(
        op, description="op", max_attempts=3, base_delay=1.0,
        retry_on=(_Boom,), sleep=sleeps.append,
    )
    assert result == "done"
    assert attempts["n"] == 3
    assert sleeps == [1.0, 2.0]  # backoff exponencial


def test_exhausts_and_raises():
    def op():
        raise _Boom("always")

    with pytest.raises(_Boom):
        retry_call(op, description="op", max_attempts=2, retry_on=(_Boom,), sleep=lambda _: None)


def test_non_listed_exception_not_retried():
    attempts = {"n": 0}

    def op():
        attempts["n"] += 1
        raise _Other("nope")

    with pytest.raises(_Other):
        retry_call(op, description="op", max_attempts=3, retry_on=(_Boom,), sleep=lambda _: None)
    assert attempts["n"] == 1  # no reintentó
