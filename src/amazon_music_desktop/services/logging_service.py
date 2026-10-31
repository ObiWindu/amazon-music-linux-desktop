"""Logging with rotating files and sensitive-data redaction."""

from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler

from .configuration import LOG_DIR

SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    # Bearer tokens must be matched before the key=value patterns below,
    # which would otherwise consume only the header name ("authorization: B")
    # and leave the credential itself in the output.
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+"),
    re.compile(r"(?i)(cookie|session|token|authorization|license)\s*[=:]\s*\S+"),
]

SENSITIVE_QUERY_KEYS = {"token", "access_token", "session", "auth", "password", "code", "state"}


def redact_text(text: str) -> str:
    out = text
    for pat in SENSITIVE_PATTERNS:
        out = pat.sub(lambda m: m.group(0).split("=")[0] + "=***REDACTED***" if "=" in m.group(0) else "***REDACTED***", out)
    return out


def sanitize_url(url: str) -> str:
    # strip query params that may be sensitive; keep host/path
    try:
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(url)
        query = parts.query
        if query:
            # drop query entirely to avoid leaking params
            query = ""
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
    except Exception:
        return url


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_text(str(record.msg))
            if record.args:
                record.args = tuple(redact_text(str(a)) if isinstance(a, str) else a for a in record.args)
        except Exception:
            pass
        return True


def setup_logging(verbosity: str = "info") -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(LOG_DIR, 0o700)
    except OSError:
        pass
    logger = logging.getLogger("amazon_music_desktop")
    logger.setLevel(logging.DEBUG if verbosity == "debug" else logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(RedactingFilter())
    logger.addHandler(file_handler)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(RedactingFilter())
    logger.addHandler(console)
    return logger


def get_logger(name: str = "amazon_music_desktop") -> logging.Logger:
    """Return a logger nested under the app logger.

    Handlers are attached to the ``amazon_music_desktop`` logger by
    ``setup_logging``; module loggers must be children of it (or their
    records never reach a handler and are silently dropped).
    """
    if name == "amazon_music_desktop":
        return logging.getLogger(name)
    return logging.getLogger(f"amazon_music_desktop.{name}")
