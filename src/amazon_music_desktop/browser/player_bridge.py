"""Bridge between native controls and the Amazon web player.

Architecture note: audio decode + Widevine decrypt run inside QtWebEngine's
media pipeline. There is no independent native audio path, so the native
buttons DRIVE the page player via JavaScript and the native bar MIRRORS the
page state (polled from the <audio> element + document.title).

This module must never mutate the page's player DOM. Earlier attempts to
hide or shrink the web player bar via CSS (display:none, then a
layout-preserving collapse) coincided with playback teardowns ~1s after
start. The page player is instead kept fully laid out and functional but
rendered outside the visible window by ``main_window._BrowserHost``: the
native bar is the only player surface visible or clickable in the app.
"""

from __future__ import annotations

from typing import Any

_ACTION_SELECTORS: dict[str, str] = {
    "previous": "[aria-label*=\"Previous\"], [data-testid*=\"previous\"]",
    "play": "[aria-label*=\"Play\"],[aria-label*=\"Pause\"], [data-testid*=\"play\"]",
    "next": "[aria-label*=\"Next\"], [data-testid*=\"next\"]",
    "shuffle": "[aria-label*=\"Shuffle\"], [data-testid*=\"shuffle\"]",
    "repeat": "[aria-label*=\"Repeat\"], [data-testid*=\"repeat\"]",
}

# Probe the page player state. Returns {title, cur, dur, paused}.
# Runs against the first <audio> element (Amazon's playback element).
NOW_PLAYING_PROBE_JS = (
    "(function(){"
    "var a=document.querySelector('audio');"
    "return {title:document.title,"
    "cur:a?a.currentTime:0,"
    "dur:a?a.duration:0,"
    "paused:a?a.paused:true};"
    "})()"
)


def player_action_js(action: str) -> str:
    """Return JS that clicks the page control for *action*.

    Returns "" for unknown actions. The snippet returns true when a control
    was found and clicked, false otherwise, so callers can log misses.
    """
    selector = _ACTION_SELECTORS.get(action)
    if selector is None:
        return ""
    return (
        f"(function(){{var b=document.querySelector('{selector}');"
        "if(!b) return false; b.click(); return true;})()"
    )


def parse_probe_result(result: Any) -> dict[str, Any] | None:
    """Normalize the probe callback payload. Returns None if unusable."""
    if not isinstance(result, dict):
        return None
    title = result.get("title")
    try:
        cur = float(result.get("cur", 0) or 0)
    except (TypeError, ValueError):
        cur = 0.0
    try:
        dur = float(result.get("dur", 0) or 0)
    except (TypeError, ValueError):
        dur = 0.0
    paused = result.get("paused", True)
    return {
        "title": title if isinstance(title, str) and title else "",
        "cur": max(cur, 0.0),
        "dur": max(dur, 0.0),
        "paused": bool(paused),
    }


def track_progress_percent(cur: float, dur: float) -> int | None:
    """Return 0-100 progress, or None when duration is unknown."""
    if dur <= 0:
        return None
    return max(0, min(100, int(cur / dur * 100)))
