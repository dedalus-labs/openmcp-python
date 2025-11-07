# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

import io
import json
import logging
from typing import Any

import pytest

from openmcp.utils.logger import ColoredFormatter, PlainFormatter, StructuredJSONFormatter, get_logger, setup_logger


def _capture_logging(level: int, *, use_json: bool, **kwargs: Any) -> list[str]:
    stream = io.StringIO()

    handler = logging.StreamHandler(stream)
    handler.setLevel(level)

    if use_json:
        serializer = kwargs.pop("json_serializer", json.dumps)
        payload_transformer = kwargs.pop("payload_transformer", None)
        handler.setFormatter(StructuredJSONFormatter(serializer, datefmt=None, payload_transformer=payload_transformer))
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))

    logger = logging.getLogger("openmcp.test.logger")
    logger.handlers = []
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False

    logger.info("greeting", extra={"context": {"value": 42}})
    handler.flush()
    logger.handlers = []
    logger.propagate = True

    return stream.getvalue().strip().splitlines()


def test_setup_logger_plain_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMCP_LOG_JSON", "0")
    setup_logger(force=True)
    log = get_logger("openmcp.test")

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    log.handlers = [handler]

    log.info("demo")
    handler.flush()

    assert stream.getvalue().strip().endswith("INFO:openmcp.test:demo")


def test_setup_logger_json_with_custom_serializer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMCP_LOG_JSON", "1")

    lines = _capture_logging(
        logging.INFO,
        use_json=True,
        json_serializer=lambda payload: json.dumps(payload),
    )

    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["logger"] == "openmcp.test.logger"
    assert payload["context"] == {"value": 42}


def test_payload_transformer_applied() -> None:
    lines = _capture_logging(
        logging.INFO,
        use_json=True,
        json_serializer=lambda payload: json.dumps(payload),
        payload_transformer=lambda payload: {
            **payload,
            "context": {"transformed": payload.get("context", {})},
        },
    )

    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["context"] == {"transformed": {"value": 42}}


def test_plain_formatter_appends_duration_suffix() -> None:
    formatter = PlainFormatter("%(message)s")
    record = logging.LogRecord("demo", logging.INFO, __file__, 0, "done", args=(), exc_info=None)
    record.duration_ms = 12.3456

    rendered = formatter.format(record)

    assert rendered.endswith("[12.35 ms]")


def test_colored_formatter_appends_duration_suffix() -> None:
    formatter = ColoredFormatter("%(message)s")
    record = logging.LogRecord("demo", logging.INFO, __file__, 0, "done", args=(), exc_info=None)
    record.duration_ms = 7.0

    rendered = formatter.format(record)

    assert "[7.00 ms]" in rendered
