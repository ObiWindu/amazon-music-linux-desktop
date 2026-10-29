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

# Locales observed live on music.amazon.fr (2026-10-29): play buttons are
# labeled "Écouter" (page header data-testid "pageHeaderPlay_Play_Button"),
# carousel/shelf pagers read "Voir l'élément suivant/précédent dans ..." with
# data-testid "*_PreviousPageButton"/"*_NextPageButton". Native controls must
# match fr + en labels, and must never hit the carousel pagers.
_ACTION_SELECTORS: dict[str, tuple[str, ...]] = {
    "previous": (
        'button[aria-label*="Précédent" i]',
        'button[aria-label*="Previous" i]',
        'button[data-testid*="prev" i]',
    ),
    "next": (
        'button[aria-label*="Suivant" i]',
        'button[aria-label*="Next" i]',
        'button[data-testid*="next" i]',
    ),
    "shuffle": (
        'button[aria-label*="aléatoire" i]',
        'button[aria-label*="Shuffle" i]',
        'button[data-testid*="shuffle" i]',
    ),
    "repeat": (
        'button[aria-label*="Répéter" i]',
        'button[aria-label*="Repeat" i]',
        'button[data-testid*="repeat" i]',
    ),
}

# Buttons whose label/testid matches this are carousel/shelf pagers or
# non-transport controls; "next"/"previous" must never page a shelf instead
# of skipping the track.
_EXCLUDE_RE = "voir l'|pagebutton|autoplay"

# Play/pause drives the page's media element directly (locale-independent),
# falling back to a control button (fr + en) when no media element exists.
_PLAY_JS = (
    "(function(){"
    "var els=document.querySelectorAll('audio,video');"
    "for(var i=0;i<els.length;i++){var el=els[i];"
    "if(el.currentSrc||el.src){"
    "if(el.paused){var p=el.play();if(p&&p.catch)p.catch(function(){});return 'play';}"
    "el.pause();return 'pause';}}"
    "var sels=['button[aria-label*=\"Pause\" i]','button[aria-label*=\"Écouter\" i]',"
    "'button[aria-label*=\"Lecture\" i]','button[aria-label*=\"Lire\" i]',"
    "'button[aria-label*=\"Play\" i]','button[data-testid*=\"play\" i]'];"
    "for(var j=0;j<sels.length;j++){var b=document.querySelector(sels[j]);"
    "if(b){b.click();return 'clicked';}}"
    "return '';"
    "})()"
)

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
    """Return JS that performs *action* against the page player.

    Returns "" for unknown actions. The snippet returns a truthy string
    describing what was done, or "" when no control matched, so callers can
    log misses. Play/pause goes through the media element itself; the other
    actions click the page's transport buttons (fr + en labels, carousel
    pagers excluded).
    """
    if action == "play":
        return _PLAY_JS
    selectors = _ACTION_SELECTORS.get(action)
    if selectors is None:
        return ""
    import json

    return (
        "(function(){"
        f"var sels={json.dumps(selectors, ensure_ascii=False)};"
        f"var ex=/{_EXCLUDE_RE}/i;"
        "for(var j=0;j<sels.length;j++){"
        "var bs=document.querySelectorAll(sels[j]);"
        "for(var i=0;i<bs.length;i++){var b=bs[i];"
        "var t=(b.getAttribute('aria-label')||'')+' '+(b.getAttribute('data-testid')||'');"
        "var r=b.getBoundingClientRect();"
        "if(ex.test(t))continue;"
        "if(r.width<8||r.height<8)continue;"
        "b.click();return 'clicked';}}"
        "}"
        "return '';"
        "})()"
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
