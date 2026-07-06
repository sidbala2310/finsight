"""Tests for the JSON log formatter."""

import json
import logging
import sys
from types import TracebackType

from finsight.logging_config import JsonFormatter

ExcInfo = (
    tuple[type[BaseException], BaseException, TracebackType | None]
    | tuple[None, None, None]
)


def _record(exc_info: ExcInfo | None = None) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=None,
        exc_info=exc_info,
    )


def test_format_produces_json_with_standard_keys() -> None:
    entry = json.loads(JsonFormatter().format(_record()))
    assert entry["level"] == "info"
    assert entry["message"] == "hello"
    assert "time" in entry
    assert "logger" in entry


def test_format_includes_exception_traceback() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record(exc_info=sys.exc_info())
    entry = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in entry["exception"]
