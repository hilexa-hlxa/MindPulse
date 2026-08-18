"""
Structured (JSON) logging setup.

Every log line — ours and the stdlib ones uvicorn/apscheduler emit —
comes out as one JSON object per line, with a request_id merged in
automatically for anything logged during a request (see
`RequestIDMiddleware` in main.py). That's the difference between
"grep the logs and hope" and being able to pipe this straight into
a log aggregator and filter by request or event.
"""
import logging
import sys

import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """Call once, at process startup, before anything logs."""
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, apscheduler, etc.) through the same
    # JSON formatter, so third-party log lines match our own output.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # uvicorn installs its own handlers; strip them so everything funnels
    # through our single JSON handler instead of double-logging.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "apscheduler", "apscheduler.scheduler"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
