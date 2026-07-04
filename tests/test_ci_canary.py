"""Temporary canary proving CI fails on bad code. Reverted before merge."""

import os


def test_deliberately_failing() -> None:
    assert 1 + 1 == 3
