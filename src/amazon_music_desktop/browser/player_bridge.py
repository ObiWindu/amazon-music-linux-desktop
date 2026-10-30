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

Transport actions use layered strategies so the page language and DOM shape
do not matter:

1. play/pause toggles the audio/video element directly (locale-free).
2. known data-testid / aria-label patterns (fr, en) click the transport
   button; pager labels are excluded so "next" never pages a shelf.
3. geometric fallback: buttons inside the docked player-bar strip of the
   page viewport are sorted by x; the cluster layout [shuffle, prev, play,
   next, repeat] is addressed relative to the play button (identified by
   label keywords, else the button nearest the viewport center).
"""

from __future__ import annotations

import json
from typing import Any

# Locales observed live on music.amazon.fr (2026-10-29): play buttons are
# labeled "Écouter" / "Pause", carousel/shelf pagers read
# "Voir l'élément suivant/précédent dans ..." with data-testid
# "*_PreviousPageButton"/"*_NextPageButton". data-testid patterns run first
# because they are not localized.
_ACTION_SELECTORS: dict[str, tuple[str, ...]] = {
    "previous": (
        'button[data-testid*="prev" i]',
        'button[aria-label*="Précédent" i]',
        'button[aria-label*="Previous" i]',
    ),
    "next": (
        'button[data-testid*="next" i]',
        'button[aria-label*="Suivant" i]',
        'button[aria-label*="Next" i]',
    ),
    "shuffle": (
        'button[data-testid*="shuffle" i]',
        'button[aria-label*="aléatoire" i]',
        'button[aria-label*="mélanger" i]',
        'button[aria-label*="Shuffle" i]',
    ),
    "repeat": (
        'button[data-testid*="repeat" i]',
        'button[aria-label*="Répéter" i]',
        'button[aria-label*="boucle" i]',
        'button[aria-label*="Repeat" i]',
    ),
    "play": (
        'button[data-testid*="play" i]',
        'button[aria-label*="Écouter" i]',
        'button[aria-label*="Lecture" i]',
        'button[aria-label*="Play" i]',
        'button[aria-label*="Pause" i]',
    ),
}

# Buttons whose label/testid matches this are carousel/shelf pagers or
# non-transport controls; "next"/"previous" must never page a shelf instead
# of skipping the track.
_EXCLUDE_RE = "voir l'|pagebutton|autoplay"

_VALID_ACTIONS = tuple(_ACTION_SELECTORS)

# Cluster layout inside Amazon's docked player bar, addressed as offsets
# from the play button (identified by label keywords, else the button
# nearest the horizontal viewport center).
_OFFSETS: dict[str, int] = {"previous": -1, "play": 0, "next": 1, "shuffle": -2, "repeat": 2}

_PLAY_LABEL_WORDS = ("play", "pause", "lecture", "lire", "Écouter")

# Probe the page player state. Returns a JSON string because QtWebEngine
# 6.11 delivers only primitive values from runJavaScript (objects and
# arrays arrive as ''); parses back to a flat state dict.
#
# document.title is NOT a reliable track name: while browsing a playlist the
# page keeps the playlist name there. navigator.mediaSession.metadata carries
# the real now-playing song (title/artist) when the page exposes it, so it
# wins when present.
NOW_PLAYING_PROBE_JS = (
    "(function(){"
    "var a=document.querySelector('audio');"
    "var md=(navigator.mediaSession&&navigator.mediaSession.metadata)?navigator.mediaSession.metadata:null;"
    "return JSON.stringify({"
    "title:(md&&md.title)?md.title:document.title,"
    "artist:(md&&md.artist)?md.artist:'',"
    "cur:a?a.currentTime:0,"
    "dur:a?a.duration:0,"
    "paused:a?a.paused:true,"
    "vol:a?a.volume:1,"
    "muted:a?a.muted:false});"
    "})()"
)

# Best-effort scrape of the page's own up-next queue rows. Tests use several
# naming conventions because Amazon's internals differ per build; an empty
# result simply means "unavailable" and the native panel keeps the songs it
# has actually seen play.
QUEUE_PROBE_JS = (
    "(function(){"
    "var sel=["
    "'[data-testid*=\"queueItem\" i]',"
    "'[data-testid*=\"queue-item\" i]',"
    "'[data-testid*=\"playQueueItem\" i]',"
    "'[data-testid*=\"upNext\" i]',"
    "'[data-testid*=\"up-next\" i]'"
    "].join(',');"
    "var rows=document.querySelectorAll(sel);"
    "var items=[];"
    "for(var i=0;i<rows.length;i++){"
    "var t=(rows[i].getAttribute('aria-label')||rows[i].textContent||'');"
    "t=t.replace(/\\s+/g,' ').trim().slice(0,80);"
    "if(t)items.push(t);}"
    "return JSON.stringify({items:items.slice(0,40)});"
    "})()"
)

# Click helper shared by every strategy: also fires pointer/mouse events so
# React-style handlers attached to those events react, not only to .click().
_CLICK_EL = (
    "var opt={bubbles:true,cancelable:true,composed:true};"
    "try{el.dispatchEvent(new PointerEvent('pointerdown',opt));}catch(e){}"
    "try{el.dispatchEvent(new MouseEvent('mousedown',opt));}catch(e){}"
    "try{el.click();}catch(e){}"
    "try{el.dispatchEvent(new PointerEvent('pointerup',opt));}catch(e){}"
    "try{el.dispatchEvent(new MouseEvent('mouseup',opt));}catch(e){}"
)

_MEDIA_FIRST = (
    "if(action==='play'){"
    "var els=document.querySelectorAll('audio,video');"
    "for(var i=0;i<els.length;i++){var el=els[i];"
    "if(el.currentSrc||el.src){"
    "if(el.paused){var p=el.play();if(p&&p.catch)p.catch(function(){});return 'play';}"
    "el.pause();return 'pause';}}}"
)

_SELECTOR_CLICKS = (
    "for(var k=0;k<sels.length;k++){"
    "var bs=document.querySelectorAll(sels[k]);"
    "for(var i=0;i<bs.length;i++){var b=bs[i];"
    "var lab=(b.getAttribute('aria-label')||'')+' '+(b.getAttribute('data-testid')||'');"
    "var r=b.getBoundingClientRect();"
    "if(ex.test(lab))continue;"
    "if(r.width<8||r.height<8)continue;"
    "var el=b;"
    "__CLICK__"
    "return 'sel:'+lab.replace(/\\s+/g,' ').trim().slice(0,60);}}"
)

_GEOMETRY_FALLBACK = (
    "var cand=[];"
    "var containers=['button','[role=button]','[role=checkbox]','[role=switch]'];"
    "for(var k=0;k<containers.length;k++){"
    "var els=document.querySelectorAll(containers[k]);"
    "for(var i=0;i<els.length;i++){var el=els[i];"
    "var r=el.getBoundingClientRect();"
    "if(r.width<24||r.height<24)continue;"
    "if(r.height>2*dock)continue;"
    "if(r.top<window.innerHeight-dock-8||r.bottom>window.innerHeight+2)continue;"
    "if(getComputedStyle(el).visibility=='hidden')continue;"
    "var lab=(el.getAttribute('aria-label')||'')+' '+(el.getAttribute('data-testid')||'');"
    "if(ex.test(lab))continue;"
    "cand.push({el:el,x:r.x+r.width/2,label:lab.replace(/\\s+/g,' ').trim().slice(0,60)});}}"
    "if(!cand.length)return '';"
    "cand.sort(function(a,b){return a.x-b.x;});"
    "var playIdx=-1;"
    "for(var i=0;i<cand.length;i++){"
    "var lw=cand[i].label.toLowerCase();"
    "for(var w=0;w<__PLAY_WORDS__.length;w++){"
    "if(lw.indexOf(__PLAY_WORDS__[w])!==-1){playIdx=i;break;}}"
    "if(playIdx>=0)break;}"
    "if(playIdx<0){var c=window.innerWidth/2;var best=1e9;"
    "for(var i=0;i<cand.length;i++){var d=Math.abs(cand[i].x-c);"
    "if(d<best){best=d;playIdx=i;}}}"
    "var offsets=__OFFSETS__;"
    "var target=playIdx+offsets[action];"
    "if(target<0||target>=cand.length)return '';"
    "var el=cand[target].el;"
    "__CLICK__"
    "return 'geom:'+cand[target].x.toFixed(0)+':'+cand[target].label;"
)

_ACTION_JS_TEMPLATE = (
    "(function(){"
    "var action=__ACTION__;"
    "var ex=/__EXCLUDE__/i;"
    "var dock=__DOCK__;"
    "var sels=__SELECTORS__;"
    "__MEDIA_FIRST__"
    "__SELECTOR_CLICKS__"
    "__GEOMETRY__"
    "return '';"
    "})()"
)


def _play_words_js() -> str:
    return "[" + ", ".join(json.dumps(word, ensure_ascii=False) for word in _PLAY_LABEL_WORDS) + "]"


def player_action_js(action: str, dock_px: int = 110) -> str:
    """Return JS that performs *action* against the page player.

    Returns "" for unknown actions. The snippet returns a non-empty string
    describing which strategy/element was used, or "" when nothing matched
    (callers log misses). Strategies: media element toggle (play), known
    selector patterns (fr/en), then the docked-strip geometry fallback.
    """
    if action not in _VALID_ACTIONS:
        return ""
    selectors = json.dumps(_ACTION_SELECTORS.get(action, ()), ensure_ascii=False)
    clicks = _SELECTOR_CLICKS.replace("__CLICK__", _CLICK_EL) if _ACTION_SELECTORS.get(action) else ""
    geometry = (
        _GEOMETRY_FALLBACK.replace("__CLICK__", _CLICK_EL)
        .replace("__OFFSETS__", json.dumps(_OFFSETS))
        .replace("__PLAY_WORDS__", _play_words_js())
    )
    return (
        _ACTION_JS_TEMPLATE.replace("__ACTION__", json.dumps(action))
        .replace("__EXCLUDE__", _EXCLUDE_RE)
        .replace("__DOCK__", str(max(0, int(dock_px))))
        .replace("__SELECTORS__", selectors)
        .replace("__MEDIA_FIRST__", _MEDIA_FIRST)
        .replace("__SELECTOR_CLICKS__", clicks)
        .replace("__GEOMETRY__", geometry)
    )


def seek_js(seconds: float) -> str:
    """Return JS that seeks the page media element to *seconds*."""
    value = max(0.0, float(seconds))
    return (
        "(function(){"
        "var a=document.querySelector('audio');"
        "if(!a){a=document.querySelector('video');}"
        "if(!a||!isFinite(a.duration)||a.duration<=0)return '';"
        f"a.currentTime=Math.max(0,Math.min(a.duration,{value}));"
        "return 'seek';"
        "})()"
    )


def volume_js(volume: float | None = None, muted: bool | None = None) -> str:
    """Return JS that sets the page media volume and/or mute flag."""
    parts = ""
    if volume is not None:
        parts += f"a.volume={max(0.0, min(1.0, float(volume)))};"
    if muted is not None:
        parts += f"a.muted={'true' if muted else 'false'};"
    if not parts:
        return ""
    return (
        "(function(){"
        "var els=document.querySelectorAll('audio,video');"
        "for(var i=0;i<els.length;i++){var a=els[i];"
        "if(!(a.currentSrc||a.src))continue;"
        "try{" + parts + "}catch(e){}"
        "return 'vol:'+a.volume+':'+(a.muted?'1':'0');}"
        "return '';"
        "})()"
    )


def parse_probe_result(result: Any) -> dict[str, Any] | None:
    """Normalize the probe callback payload. Returns None if unusable.

    Accepts the JSON string the probe returns (QtWebEngine 6.11 delivers
    object results as empty strings, so probes stringify) and, for stacks
    that deliver dicts directly, the dict form.
    """
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (ValueError, TypeError):
            return None
    if not isinstance(result, dict):
        return None

    def _float(value: Any, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            return max(float(value), 0.0)
        except (TypeError, ValueError):
            return default

    title = result.get("title")
    volume = min(_float(result.get("vol"), 1.0), 1.0)
    artist = result.get("artist")
    return {
        "title": title if isinstance(title, str) and title else "",
        "artist": artist if isinstance(artist, str) else "",
        "cur": _float(result.get("cur")),
        "dur": _float(result.get("dur")),
        "paused": bool(result.get("paused", True)),
        "volume": volume,
        "muted": bool(result.get("muted", False)),
    }


def parse_queue_result(result: Any) -> list[str] | None:
    """Normalize the queue-scrape payload. None when unusable."""
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (ValueError, TypeError):
            return None
    if not isinstance(result, dict):
        return None
    items = result.get("items")
    if not isinstance(items, list):
        return None
    return [str(item) for item in items if isinstance(item, str) and item.strip()]


def track_progress_percent(cur: float, dur: float) -> int | None:
    """Return 0-100 progress, or None when duration is unknown."""
    if dur <= 0:
        return None
    return max(0, min(100, int(cur / dur * 100)))
