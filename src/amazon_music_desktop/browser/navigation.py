"""Navigation and origin security policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit


class NavigationDecision(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    EXTERNAL = "external"
    DOWNLOAD = "download"


# Trusted registrable suffixes. Hostname boundary is enforced: a host matches
# only if it equals the suffix or ends with "." + suffix.
TRUSTED_HOST_SUFFIXES: tuple[str, ...] = (
    "amazon.fr",
    "amazon.com",
    "amazon.co.uk",
    "amazon.de",
    "amazon.ca",
    "amazon.it",
    "amazon.es",
    "amazon.in",
    "amazon.co.jp",
    "amazon.com.au",
    "amazon.com.br",
    "amazon.nl",
    "amazon.se",
    "amazon.pl",
    "amazon.com.mx",
    "media-amazon.com",
    "ssl-images-amazon.com",
    "images-amazon.com",
    "m.media-amazon.com",
)

ALLOWED_SCHEMES = {"https", "http", "about", "qrc", "chrome", "chrome-error", "data"}


def _host_matches(host: str, suffix: str) -> bool:
    host = host.lower().rstrip(".")
    suffix = suffix.lower().rstrip(".")
    return host == suffix or host.endswith("." + suffix)


def is_trusted_host(host: str) -> bool:
    if not host:
        return False
    # strip userinfo already handled by caller via urlsplit hostname
    # reject obvious tricks
    if "@" in host or "\\" in host:
        return False
    for suffix in TRUSTED_HOST_SUFFIXES:
        if _host_matches(host, suffix):
            return True
    return False


def classify_url(url: str) -> NavigationDecision:
    if not url:
        return NavigationDecision.BLOCK
    try:
        parts = urlsplit(url)
    except ValueError:
        return NavigationDecision.BLOCK
    scheme = (parts.scheme or "").lower()
    if scheme in ("javascript", "vbscript", "file", "ftp", "intent"):
        return NavigationDecision.BLOCK
    if scheme == "data":
        # allow data: only for subresources handled by browser; block top-level nav
        return NavigationDecision.BLOCK
    if scheme in ("http", "https"):
        host = parts.hostname or ""
        if is_trusted_host(host):
            return NavigationDecision.ALLOW
        return NavigationDecision.EXTERNAL
    if scheme in ("about", "qrc", "chrome", "chrome-error"):
        return NavigationDecision.ALLOW
    # unknown scheme
    return NavigationDecision.BLOCK


@dataclass
class NavigationPolicy:
    allow_external_in_system_browser: bool = True

    def decide(self, url: str) -> NavigationDecision:
        return classify_url(url)
