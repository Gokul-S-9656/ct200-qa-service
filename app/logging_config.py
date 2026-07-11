"""
Logging setup.

The original app had a single `print()` in the startup path and nothing
elsewhere. That's fine for a local demo but useless in production: no
timestamps, no severity levels, nothing to grep or ship to a log
aggregator, and no way to turn verbosity up/down without editing code.

This configures the stdlib `logging` module once, at import time, so
every module can do `logging.getLogger(__name__)` and get consistent,
leveled, timestamped output without repeating setup.
"""
import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        # Idempotent: pytest imports app.main multiple times across test
        # runs/modules, and duplicate handlers would duplicate every
        # log line.
        return

    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s :: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.addHandler(handler)

    # httpx logs full request/response details at DEBUG, which would
    # include the Groq Authorization header -- keep it at WARNING
    # regardless of our own app's log level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
