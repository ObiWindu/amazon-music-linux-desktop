"""Bridge for fetching the user's Amazon Music playlists and their songs.

Like ``player_bridge``, everything here is read-only JavaScript against the
page DOM: the page is never mutated from Python (see the architecture note
there — touching the page's player DOM correlated with playback teardowns).

Two probes run against whatever page is loaded (the visible view for the
playlists index, an offscreen ``QWebEnginePage`` for individual playlists so
queuing a playlist never disturbs the page that is playing):

* ``PLAYLISTS_PROBE_JS`` scrapes playlist cards/links (name + absolute href)
  from a playlists index page.
* ``PLAYLIST_SONGS_PROBE_JS`` scrapes the track rows of a playlist page into
  ``{title, artist}`` items.
* ``PLAY_FIRST_SONG_JS`` clicks the first track row (or, as a fallback, the
  playlist header's play button outside the docked player strip) so a
  double-clicked playlist starts playing its first song.

All probes return JSON strings because QtWebEngine 6.11 delivers only
primitive values from ``runJavaScript``; the ``parse_*`` functions accept
both the JSON string and a plain dict (for stacks/tests that deliver dicts).
Amazon's internals differ per build, so selectors follow several naming
conventions; an empty result simply means "unavailable".
"""

from __future__ import annotations

import json
from typing import Any

_MAX_PLAYLISTS = 60
_MAX_SONGS = 200

# Scrape playlist entries (name + href) from a playlists index page. The
# index link itself ("/my/playlists") is skipped so only real playlists are
# listed. Anchors win because el.href is absolute; card containers refine
# the name when the anchor text is noisy.
PLAYLISTS_PROBE_JS = (
    "(function(){"
    "var items=[];var seen={};"
    "var anchors=document.querySelectorAll('a[href*=\"/playlists/\"]');"
    "for(var i=0;i<anchors.length&&items.length<" + str(_MAX_PLAYLISTS) + ";i++){"
    "var a=anchors[i];"
    "var href='';"
    "try{href=a.href||a.getAttribute('href')||'';}catch(e){href=a.getAttribute('href')||'';}"
    "if(!href)continue;"
    "var path=href.split('?')[0].split('#')[0].replace(/\\/+$/,'');"
    "if(!/\\/playlists\\/.+/.test(path))continue;"
    "if(seen[href])continue;"
    "var name=(a.getAttribute('aria-label')||a.textContent||'').replace(/\\s+/g,' ').trim();"
    "var card=null;"
    "try{card=a.closest('[data-testid*=\"playlist\" i]');}catch(e){}"
    "if(card){"
    "var n=(card.getAttribute('aria-label')||card.textContent||'').replace(/\\s+/g,' ').trim();"
    "if(n.length>name.length)name=n;}"
    "if(!name||name.length>120)continue;"
    "seen[href]=1;"
    "items.push({name:name.slice(0,80),href:href});"
    "}"
    "return JSON.stringify({items:items});"
    "})()"
)

# Scrape the track rows of a playlist page into {title, artist} items.
# Title/artist child elements are preferred; the row's aria-label/text is
# the fallback. Rows are deduped by title+artist and capped.
_PLAYLIST_ROW_SELECTORS = (
    '[data-testid*="track" i],'
    '[data-testid*="song" i],'
    '[data-testid*="musicRow" i],'
    '[data-testid*="playQueueItem" i],'
    'li[role="row"]'
)

PLAYLIST_SONGS_PROBE_JS = (
    "(function(){"
    "var rows=document.querySelectorAll(" + json.dumps(_PLAYLIST_ROW_SELECTORS) + ");"
    "function txt(el){return ((el&&el.textContent)||'').replace(/\\s+/g,' ').trim();}"
    "var items=[];var seen={};"
    "for(var i=0;i<rows.length&&items.length<" + str(_MAX_SONGS) + ";i++){"
    "var r=rows[i];"
    "var rect=r.getBoundingClientRect();"
    "if(rect.width<40||rect.height<16)continue;"
    "var t=r.querySelector('[data-testid*=\"title\" i],[data-testid*=\"name\" i],[class*=\"title\" i],[class*=\"Title\" i]');"
    "var a=r.querySelector('[data-testid*=\"artist\" i],[data-testid*=\"subtitle\" i],[class*=\"artist\" i],[class*=\"Artist\" i],[class*=\"secondary\" i]');"
    "var title=t?txt(t):'';"
    "var artist=a?txt(a):'';"
    "if(!title){"
    "var label=(r.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim();"
    "if(label){var parts=label.split(/\\s+[—–-]\\s+/);title=parts[0].slice(0,80);artist=(parts[1]||'').slice(0,80);}"
    "else{title=txt(r).slice(0,80);}}"
    "title=(title||'').slice(0,80);artist=(artist||'').slice(0,80);"
    "if(!title)continue;"
    "var key=title+'\\u0001'+artist;"
    "if(seen[key])continue;"
    "seen[key]=1;"
    "items.push({title:title,artist:artist});"
    "}"
    "return JSON.stringify({items:items});"
    "})()"
)

# Shared click helper (same event fan-out as player_bridge so React-style
# handlers react, not only .click()).
_CLICK_EL = (
    "var opt={bubbles:true,cancelable:true,composed:true};"
    "try{el.dispatchEvent(new PointerEvent('pointerdown',opt));}catch(e){}"
    "try{el.dispatchEvent(new MouseEvent('mousedown',opt));}catch(e){}"
    "try{el.click();}catch(e){}"
    "try{el.dispatchEvent(new PointerEvent('pointerup',opt));}catch(e){}"
    "try{el.dispatchEvent(new MouseEvent('mouseup',opt));}catch(e){}"
)

# Click the first track row of a playlist page so playback starts on the
# first song. Rows inside the docked player strip (bottom DOCK_PX of the
# viewport) are never clicked. Fallback: the header play button, again
# excluding the docked strip.
PLAY_FIRST_SONG_JS = (
    "(function(){"
    "var dock=__DOCK__;"
    "var rows=document.querySelectorAll(" + json.dumps(_PLAYLIST_ROW_SELECTORS) + ");"
    "for(var i=0;i<rows.length;i++){"
    "var r=rows[i];var rect=r.getBoundingClientRect();"
    "if(rect.width<40||rect.height<20)continue;"
    "if(rect.top<0||rect.bottom>window.innerHeight-dock+8)continue;"
    "var btn=r.querySelector('button[data-testid*=\"play\" i],button[aria-label*=\"Écouter\" i],button[aria-label*=\"Play\" i]');"
    "var el=btn||r;"
    "__CLICK__"
    "return 'row:'+i;"
    "}"
    "var btns=document.querySelectorAll('button[data-testid*=\"play\" i],button[aria-label*=\"Écouter\" i],button[aria-label*=\"Play\" i],button[aria-label*=\"Lecture\" i]');"
    "for(var i=0;i<btns.length;i++){"
    "var b=btns[i];var r2=b.getBoundingClientRect();"
    "if(r2.width<24||r2.height<24)continue;"
    "if(r2.bottom>window.innerHeight-dock+8)continue;"
    "var el=b;"
    "__CLICK__"
    "return 'playbtn';"
    "}"
    "return '';"
    "})()"
).replace("__CLICK__", _CLICK_EL)


def play_first_song_js(dock_px: int = 110) -> str:
    """Return JS that starts playing the first song of the loaded playlist page."""
    return PLAY_FIRST_SONG_JS.replace("__DOCK__", str(max(0, int(dock_px))))


def parse_playlists_result(result: Any) -> list[dict[str, str]] | None:
    """Normalize the playlists-scrape payload to [{name, href}], or None."""
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
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        href = item.get("href")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(href, str) or not href.strip():
            continue
        out.append({"name": name.strip(), "href": href.strip()})
    return out


def parse_playlist_songs_result(result: Any) -> list[dict[str, str]] | None:
    """Normalize the playlist-songs payload to [{title, artist}], or None."""
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
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        artist = item.get("artist")
        if not isinstance(title, str) or not title.strip():
            continue
        out.append(
            {
                "title": title.strip(),
                "artist": artist.strip() if isinstance(artist, str) else "",
            }
        )
    return out
