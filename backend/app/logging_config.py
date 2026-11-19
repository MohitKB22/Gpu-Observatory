"""Structured logging setup.

In JSON mode every log line is a single JSON object, which log shippers (Loki, CloudWatch,
Datadog, ...) can index without custom parsing. Values passed through `extra=` become fields.
"""

import json
import logging
import sys
from datetime import UTC, datetime

# Attributes every LogRecord has; anything else on the record came from `extra=`.
_STANDARD_RECORD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", log_format: str = "json") -> None:
    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # We log each HTTP request ourselves (with a request id), so uvicorn's access log is redundant.
    logging.getLogger("uvicorn.access").disabled = True
    # httpx logs every outbound request at INFO, which would duplicate inference logging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
