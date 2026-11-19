"""Logging setup shared by the API process and the seed script."""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Send logs to stderr with a timestamp, level, and logger name.

    ``force=True`` replaces any earlier basicConfig so the seed script and
    the API agree on one format even if a library configured logging first.
    """
    numeric = getattr(logging, (level or "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
