"""Simulated `spike.control` module: timing helpers used by FLL programs."""

from . import spike_api


def wait_for_seconds(seconds):
    spike_api._ctx().advance(float(seconds))


def wait_until(predicate, get_value=None, target=None):
    # SPIKE's real signature is wait_until(get_value, operator, target); we
    # accept either a bare predicate callable or that 3-arg form.
    if get_value is None and target is None:
        spike_api._wait_until(lambda: bool(predicate()))
        return
    op = predicate  # operator function like operator.eq
    spike_api._wait_until(lambda: op(get_value(), target))


class Timer:
    """A stopwatch measured in simulated time."""

    def __init__(self):
        self._start = spike_api._ctx().t

    def reset(self):
        self._start = spike_api._ctx().t

    def now(self):
        return round(spike_api._ctx().t - self._start, 2)
