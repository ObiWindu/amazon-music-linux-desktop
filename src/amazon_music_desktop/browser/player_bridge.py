"""Bridge between native controls and the Amazon web player.

Architecture note: audio decode + Widevine decrypt run inside QtWebEngine's
media pipeline. There is no independent native audio path, so the native
buttons DRIVE the page player via JavaScript and the native bar MIRRORS the
page state (polled from the <audio> element + document.title).

Visual minimization must never use ``display:none``, ``visibility:hidden``,
node removal, or broad selectors (``footer``, ``[class*="player"]``): ripping
the player UI out of layout breaks Amazon's PlaybackAdapter and kills audio
after ~1s. Instead we collapse only the bottom-docked bar in a
layout-preserving way, and never touch elements containing audio/video.
"""

from __future__ import annotations

from typing import Any

MINIMIZED_BAR_CLASS = "amd-minimized-player-bar"

# Layout-preserving: element stays in DOM and keeps its box (no display:none,
# no visibility:hidden), so page JS layout measurements and the media pipeline
# keep working. Only visual height/opacity and pointer events are reduced.
PLAYER_BAR_STYLE = (
    f".{MINIMIZED_BAR_CLASS} {{\n"
    "  max-height: 8px !important;\n"
    "  overflow: hidden !important;\n"
    "  opacity: 0.2 !important;\n"
    "  pointer-events: none !important;\n"
    "}\n"
)

# Finds bottom-docked bar strips, adds the minimizing class, and skips any
# candidate containing audio/video elements. Returns the number minimized.
# Safe to re-run (idempotent): already-classed elements are skipped.
MINIMIZE_BAR_JS = (
    "(function(){\n"
    f"  var cls='{MINIMIZED_BAR_CLASS}';\n"
    "  var vh=window.innerHeight, vw=window.innerWidth, n=0;\n"
    "  var els=document.querySelectorAll('body div');\n"
    "  for (var i=0;i<els.length;i++){\n"
    "    var el=els[i];\n"
    "    if (el.classList.contains(cls)) continue;\n"
    "    if (el.querySelector('audio,video')) continue;\n"
    "    var r=el.getBoundingClientRect();\n"
    "    if (r.width < vw*0.6) continue;\n"
    "    if (r.height < 24 || r.height > vh*0.45) continue;\n"
    "    if (Math.abs(vh-r.bottom) > 4) continue;\n"
    "    el.classList.add(cls); n++;\n"
    "  }\n"
    "  return n;\n"
    "})()"
)

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
