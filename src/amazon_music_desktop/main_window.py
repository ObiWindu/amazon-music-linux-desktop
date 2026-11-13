"""Main application window (Amazon Music-like shell)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .browser.download_policy import default_download_dir, safe_filename, validate_destination
from .browser.navigation import NavigationDecision, NavigationPolicy
from .browser.playback_diagnostics import PlaybackDiagnostics
from .browser.playback_monitor import PLAYBACK_MONITOR_JS, PlaybackMonitor, PlaybackState
from .browser.player_bridge import (
    NOW_PLAYING_PROBE_JS,
    QUEUE_PROBE_JS,
    parse_probe_result,
    parse_queue_result,
    player_action_js,
    seek_js,
    volume_js,
)
from .browser.playlist_bridge import (
    PLAYLIST_SONGS_PROBE_JS,
    PLAYLISTS_PROBE_JS,
    parse_playlist_songs_result,
    parse_playlists_result,
    play_first_song_js,
)
from .browser.profile import ProfileManager
from .integrations.mpris import MprisService
from .services.configuration import ConfigService
from .services.desktop_integration import create_tray, tray_available
from .services.logging_service import get_logger
from .ui.now_playing import NowPlayingWidget
from .ui.player_bar import PlayerBar
from .ui.queue_panel import QueuePanel
from .ui.settings_page import SettingsPage

log = get_logger("main_window")

# Toggle buttons whose local checked state must track the page: a click
# flips the button optimistically, and a missed page action flips it back
# so the bar never claims a mode the page did not take.
_TOGGLE_BUTTON_ATTRS = {"shuffle": "shuffle_btn", "repeat": "repeat_btn"}

# Client-side ("soft") navigation for the Amazon SPA. A full view.load()
# reloads the document and tears down the page's media element, which stops
# playback and reboots the SPA (so a route like the favorites filter never
# sticks). Pushing the URL and dispatching popstate lets the SPA's own
# router render the route inside the same document, so the player keeps
# playing. Only a target that cannot be pushed same-origin falls back to a
# full load.
_SOFT_NAV_JS = (
    "(function(){"
    "var target=__URL__;"
    "try{"
    "var u=new URL(target,location.href);"
    "if(u.origin!==location.origin)return 'cross-origin';"
    "if(location.href===u.href)return 'same';"
    "history.pushState(history.state,'',u.href);"
    "window.dispatchEvent(new PopStateEvent('popstate',{state:history.state}));"
    "return location.href===u.href?'pushed':'failed';"
    "}catch(e){return 'error';}"
    "})()"
)


class WebPage(QWebEnginePage):
    def __init__(self, profile, policy, diagnostics=None, parent=None):
        super().__init__(profile, parent)
        self.policy = policy
        self.diagnostics = diagnostics

    def javaScriptConsoleMessage(self, level, message, line, source):
        log.info("JS console: %s %s (line %s)", level, message, line)
        diagnostics = self.diagnostics
        if diagnostics is not None and level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            diagnostics.record_console_error(message, source=source, line=line)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        decision = self.policy.decide(url.toString())
        if decision == NavigationDecision.BLOCK:
            log.warning("blocked navigation: %s", url.toString()[:120])
            return False
        if decision == NavigationDecision.EXTERNAL:
            try:
                subprocess.Popen(["xdg-open", url.toString()])
            except Exception as exc:
                log.warning("xdg-open failed: %s", exc)
            return False
        return True

    def createWindow(self, window_type):
        return None


def _sidebar_button(text: str, tooltip: str) -> QPushButton:
    b = QPushButton(text)
    b.setToolTip(tooltip)
    b.setFlat(True)
    b.setStyleSheet(
        "QPushButton { text-align: left; padding: 10px 14px; border: none; "
        "border-radius: 8px; color: #e8e4ff; background: transparent; font-size: 13px; }"
        "QPushButton:hover { background: #2e2847; }"
        "QPushButton:checked { background: #7c6af7; color: white; }"
    )
    b.setCheckable(True)
    return b


class _BrowserHost(QWidget):
    """Hosts the web view so the page's bottom-docked player bar never shows.

    The view is sized taller than the host (host height + DOCK_PX). The page
    viewport is therefore taller than the visible area, so Amazon's
    bottom-docked player bar is laid out below the host rect. Qt clips child
    widgets to their parent, so that strip is never painted and never
    receives input, while the page keeps a fully functional player: no CSS,
    DOM, or layout interference — the native bottom bar is the only player
    surface visible and clickable in the app window.
    """

    DOCK_PX = 110

    def __init__(self, view: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self._view = view
        view.setParent(self)
        view.move(0, 0)
        view.resize(self.width(), self.height() + self.DOCK_PX)
        view.show()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._view.resize(self.width(), self.height() + self.DOCK_PX)


class MainWindow(QMainWindow):
    def __init__(self, config_service: ConfigService, profile_manager: ProfileManager, profile, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.profile_manager = profile_manager
        self.profile = profile
        self.policy = NavigationPolicy()

        self.setWindowTitle("Amazon Music Desktop")
        self.setMinimumSize(QSize(1000, 640))
        self._last_dur = 0.0
        self._track_key = ""
        self._poll_count = 0
        self._track_title = ""
        self._track_artist = ""
        self._encrypted_noted_at = 0.0
        self._last_media_session_state = ""
        # playlist fetching state: an offscreen page loads playlist URLs so
        # queuing a playlist never navigates (or stops playback on) the
        # visible view. A token guards against stale async results.
        self._fetch_token = 0
        self._fetch_href = ""
        self._fetch_pending: tuple[int, Callable[[list[dict[str, str]]], None]] | None = None
        self._fetch_attempts = 0
        self._playlist_song_cache: dict[str, list[dict[str, str]]] = {}
        self._pending_play_href = ""
        self._play_first_armed = False
        self._play_first_done = False

        # playback observability (remediation spec 3): the monitor normalizes
        # browser media events, the diagnostics collector classifies failures.
        self.playback_diagnostics = PlaybackDiagnostics()
        self.monitor = PlaybackMonitor(on_state_changed=self._on_playback_state_changed)

        # central: sidebar + stacked content
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(180)
        sidebar.setStyleSheet("background: #211d33; border-right: 1px solid #3d365e;")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(10, 16, 10, 16)
        sb_layout.setSpacing(4)

        title = QLabel("Amazon Music")
        title.setStyleSheet("color: #c4b5fd; font-size: 16px; font-weight: bold; padding: 8px;")
        sb_layout.addWidget(title)

        self.now_playing = NowPlayingWidget()
        sb_layout.addWidget(self.now_playing)

        # Text-only labels: colorful emoji glyphs clash with the purple
        # theme (same rule as the vector transport icons in player_bar).
        self.btn_home = _sidebar_button("Home", "Home")
        self.btn_search = _sidebar_button("Search", "Search")
        self.btn_library = _sidebar_button("Library", "Library")
        self.btn_playlists = _sidebar_button("Playlists", "Playlists — fetches and lists your playlists below")
        self.btn_favorites = _sidebar_button("Favorites", "Favorites")
        for b in (self.btn_home, self.btn_search, self.btn_library, self.btn_playlists):
            sb_layout.addWidget(b)

        # user playlists fetched from the page, shown below the Playlists
        # button. Single click queues all songs, double click clears the
        # queue, queues the playlist and plays its first song.
        self.playlist_list = QListWidget()
        self.playlist_list.setObjectName("playlistList")
        self.playlist_list.setVisible(False)
        self.playlist_list.setMaximumHeight(180)
        sb_layout.addWidget(self.playlist_list)

        sb_layout.addWidget(self.btn_favorites)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #b8aee6; font-size: 11px; padding: 4px 8px;")
        self.status_label.setWordWrap(True)
        sb_layout.addWidget(self.status_label)

        sb_layout.addStretch()

        self.btn_settings = _sidebar_button("Settings", "Settings")
        self.btn_diagnostics = _sidebar_button("Diagnostics", "Diagnostics")
        self.btn_queue = _sidebar_button("Queue", "Queue")
        sb_layout.addWidget(self.btn_settings)
        sb_layout.addWidget(self.btn_diagnostics)
        sb_layout.addWidget(self.btn_queue)

        root.addWidget(sidebar)

        # stacked content
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # queue panel created later

        # browser page: the view is docked with its bottom strip (where the
        # page's own player bar renders) outside the visible window area.
        self.view = QWebEngineView()
        self.page = WebPage(self.profile, self.policy, self.playback_diagnostics, self.view)
        self.view.setPage(self.page)
        self.browser_page = _BrowserHost(self.view)
        self.stack.addWidget(self.browser_page)

        # Offscreen page (no view) used to fetch playlist contents: it shares
        # the profile (so it is authenticated) but loading it never touches
        # the visible view, so queuing a playlist cannot stop playback.
        self._fetcher_page = WebPage(self.profile, self.policy, None, self)
        self._fetcher_page.loadFinished.connect(self._on_fetcher_load_finished)

        # settings page
        self.settings_page = SettingsPage(self.config_service.config)
        self.stack.addWidget(self.settings_page)

        # bottom bar: native player with animated transport controls. The
        # page's own player bar stays docked out of view; the native bar
        # mirrors it and drives it through browser.player_bridge.
        self.player_bar = PlayerBar(self)
        self.player_bar.play_btn.clicked.connect(lambda: self._player_js("play"))
        self.player_bar.prev_btn.clicked.connect(lambda: self._player_js("previous"))
        self.player_bar.next_btn.clicked.connect(lambda: self._player_js("next"))
        self.player_bar.shuffle_btn.clicked.connect(lambda: self._player_js("shuffle"))
        self.player_bar.repeat_btn.clicked.connect(lambda: self._player_js("repeat"))
        self.player_bar.volume_changed.connect(self._set_player_volume)
        self.player_bar.muted_changed.connect(self._set_player_muted)
        self.player_bar.seek_requested.connect(self._apply_player_seek)

        # place bottom bar below central content
        # restructure: use a vertical layout containing stack+bottom
        # Rebuild central properly
        central.deleteLater()
        central2 = QWidget(self)
        self.setCentralWidget(central2)
        outer_layout = QVBoxLayout(central2)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        # top row: sidebar + stack + right queue panel
        self.queue_panel = QueuePanel()
        top_row = QWidget()
        tr = QHBoxLayout(top_row)
        tr.setContentsMargins(0, 0, 0, 0)
        tr.setSpacing(0)
        tr.addWidget(sidebar)
        tr.addWidget(self.stack, 1)
        tr.addWidget(self.queue_panel)

        outer_layout.addWidget(top_row, 1)
        outer_layout.addWidget(self.player_bar)

        # web settings
        ws = self.page.settings()
        ws.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        ws.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        # The native bar drives the page's media element programmatically;
        # without this QtWebEngine blocks play() outside a user gesture.
        ws.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)

        # signals
        self.view.urlChanged.connect(self._on_url_changed)

        self._np_timer = QTimer(self)
        self._np_timer.timeout.connect(self._poll_now_playing)
        self._np_timer.start(1000)
        self.view.loadStarted.connect(self._on_load_started)
        self.view.loadProgress.connect(self._on_load_progress)
        self.view.loadFinished.connect(self._on_load_finished)
        self.page.renderProcessTerminated.connect(self._on_render_terminated)
        self.profile.downloadRequested.connect(self._on_download_requested)

        # desktop integration: MPRIS after the page and widgets exist. On
        # systems without a session bus the service simply stays unregistered.
        self.mpris = MprisService(self)

        # wire
        self.btn_home.clicked.connect(lambda: self._nav("home"))
        self.btn_search.clicked.connect(lambda: self._nav("search"))
        self.btn_library.clicked.connect(lambda: self._nav("library"))
        self.btn_playlists.clicked.connect(self.show_playlists)
        self.playlist_list.itemClicked.connect(self._on_playlist_clicked)
        self.playlist_list.itemDoubleClicked.connect(self._on_playlist_double_clicked)
        self.btn_favorites.clicked.connect(lambda: self._nav("favorites"))
        self.btn_settings.clicked.connect(self.show_settings)
        self.btn_diagnostics.clicked.connect(self.show_diagnostics)
        self.btn_queue.clicked.connect(self.toggle_queue)
        self.settings_page.apply_btn.clicked.connect(self.apply_settings)
        self.settings_page.reset_btn.clicked.connect(self.reset_settings)
        self.settings_page.set_playback_actions(
            run=self.show_diagnostics,
            copy_report=self._copy_playback_report,
            open_docs=self._open_troubleshooting,
        )

        self._setup_tray()
        self._setup_shortcuts()

        cfg = self.config_service.config
        url = cfg.last_url or cfg.homepage_url
        if not url:
            url = self.config_service.region_url()
        self.view.load(QUrl(url))
        self._set_active(self.btn_home)

    def _set_active(self, btn):
        for b in (self.btn_home, self.btn_search, self.btn_library, self.btn_playlists, self.btn_favorites):
            b.setChecked(b is btn)

    def _region_base(self) -> str:
        return self.config_service.config.homepage_url.rstrip("/")

    def _nav(self, section: str):
        base = self._region_base()
        mapping = {
            "home": base + "/",
            "search": base + "/search",
            "library": base + "/my/library",
            "playlists": base + "/my/playlists",
            "favorites": base + "/my/music?filter=FAVORITES",
        }
        url = mapping.get(section, base + "/")
        self._soft_navigate(url)
        self._set_active({
            "home": self.btn_home, "search": self.btn_search, "library": self.btn_library,
            "playlists": self.btn_playlists, "favorites": self.btn_favorites,
        }[section])
        self.stack.setCurrentWidget(self.browser_page)

    def _soft_navigate(self, url: str) -> None:
        """Navigate the SPA without a document reload so playback never stops.

        Sidebar buttons (Home/Search/Library/Playlists/Favorites) must not
        interrupt the current song: a full ``view.load()`` destroys the
        page's media element. The URL is pushed and a popstate dispatched so
        the page's own router renders the route in the same document. Only a
        target that cannot be pushed same-origin falls back to a full load.
        """
        if self.current_url() == url:
            return
        js = _SOFT_NAV_JS.replace("__URL__", json.dumps(url))
        try:
            self.view.page().runJavaScript(
                js, lambda result, u=url: self._on_soft_nav_result(u, result)
            )
        except Exception as exc:
            log.warning("soft navigation failed to start: %s", exc)
            self.view.load(QUrl(url))

    def _on_soft_nav_result(self, url: str, result) -> None:
        if result in ("pushed", "same"):
            return
        log.info("soft navigation to %s returned %r; falling back to full load", url, result)
        self.view.load(QUrl(url))

    def show_settings(self):
        self.stack.setCurrentWidget(self.settings_page)
        self._set_active(self.btn_settings)

    def show_diagnostics(self):
        from .ui.diagnostics_dialog import DiagnosticsDialog
        DiagnosticsDialog(self, playback_diagnostics=self.playback_diagnostics).exec()

    def _playback_diagnostics_report(self) -> str:
        """Assemble the full, redacted diagnostic report (spec 5)."""
        from .ui.diagnostics_dialog import DiagnosticsDialog
        return DiagnosticsDialog(self, playback_diagnostics=self.playback_diagnostics).build_report()

    def _copy_playback_report(self) -> None:
        try:
            QApplication.clipboard().setText(self._playback_diagnostics_report())
            self.status_label.setText("Diagnostic report copied")
        except Exception as exc:
            log.warning("copy diagnostic report failed: %s", exc)

    def _open_troubleshooting(self) -> None:
        doc = Path(__file__).resolve().parents[2] / "docs" / "TROUBLESHOOTING.md"
        if doc.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(doc)))
        else:
            self.status_label.setText(f"Documentation not found: {doc.name}")

    def toggle_queue(self):
        self.queue_panel.setVisible(not self.queue_panel.isVisible())

    def show_playlists(self):
        """Playlists button: open the playlists page and fetch the list below it."""
        self._nav("playlists")
        # the SPA renders after load; probe a few times until cards appear
        for delay in (1500, 4000, 8000):
            QTimer.singleShot(delay, self._request_playlists)

    def _request_playlists(self):
        """Scrape the user's playlists from the current page into the sidebar list."""
        try:
            self.view.page().runJavaScript(PLAYLISTS_PROBE_JS, self._on_playlists_result)
        except Exception as exc:
            log.warning("playlists probe failed: %s", exc)

    def _on_playlists_result(self, result):
        items = parse_playlists_result(result)
        if items:
            self._set_playlists(items)

    def _set_playlists(self, items) -> None:
        """Rebuild the sidebar playlist list; an unchanged scrape is a no-op."""
        new = [(str(it.get("name") or ""), str(it.get("href") or "")) for it in items]
        current = []
        for index in range(self.playlist_list.count()):
            row = self.playlist_list.item(index)
            current.append((row.text(), row.data(Qt.ItemDataRole.UserRole) or ""))
        if current == new:
            return
        self.playlist_list.clear()
        for name, href in new:
            item = QListWidgetItem(name)
            item.setToolTip(href)
            item.setData(Qt.ItemDataRole.UserRole, href)
            self.playlist_list.addItem(item)
        self.playlist_list.setVisible(bool(new))

    def _on_playlist_clicked(self, item) -> None:
        """Single click on a playlist: add all its songs to the player queue."""
        href = item.data(Qt.ItemDataRole.UserRole) if item is not None else ""
        if not href:
            return
        name = item.text()
        self.status_label.setText(f"Fetching songs of {name}…")
        self._fetch_playlist_songs(href, lambda songs, n=name: self._queue_playlist_songs(n, songs))

    def _on_playlist_double_clicked(self, item) -> None:
        """Double click: clear the queue, add the playlist, play its first song."""
        href = item.data(Qt.ItemDataRole.UserRole) if item is not None else ""
        if not href:
            return
        name = item.text()
        self.status_label.setText(f"Loading {name}…")
        self._fetch_playlist_songs(href, lambda songs, n=name, h=href: self._play_playlist(n, h, songs))

    @staticmethod
    def _is_playlist_url(url: str) -> bool:
        return "/playlists/" in url.split("?")[0].split("#")[0]

    def _maybe_queue_current_playlist(self) -> None:
        """A playlist started playing from the page: queue all its songs.

        The queue panel otherwise learns only the song being played (one row
        per track change). When the current page URL is a playlist, fetch the
        full track list through the offscreen page (cached per URL) and add
        every song to the player queue; songs already queued are skipped.
        """
        url = self.current_url()
        if not self._is_playlist_url(url):
            return
        name = url.rstrip("/").split("/")[-1] or "playlist"
        self._fetch_playlist_songs(url, lambda songs, n=name: self._queue_playlist_songs(n, songs))

    def _queue_playlist_songs(self, name: str, songs: list[dict[str, str]]) -> None:
        if not songs:
            self.status_label.setText(f"No songs found for {name}")
            return
        # from now on the panel is user-managed: the page scrape must not
        # wipe the queued songs on the next poll
        self.queue_panel.set_manual_queue(True)
        added = self.queue_panel.add_songs(songs)
        self.status_label.setText(f"Added {added} songs from {name} to the queue")

    def _play_playlist(self, name: str, href: str, songs: list[dict[str, str]]) -> None:
        self.queue_panel.set_manual_queue(True)
        self.queue_panel.clear_queue()
        added = self.queue_panel.add_songs(songs)
        self.status_label.setText(f"Playing {name} ({added} songs queued)")
        # Playback authority stays the visible page: navigate it to the
        # playlist (soft, so a playing song is not interrupted), then click
        # the first song once the SPA has rendered.
        self._pending_play_href = href
        self._play_first_armed = True
        self._play_first_done = False
        self._soft_navigate(href)

    def _fetch_playlist_songs(self, href: str, callback) -> None:
        """Fetch a playlist's songs through the offscreen page (cached by href)."""
        cached = self._playlist_song_cache.get(href)
        if cached is not None:
            callback(cached)
            return
        self._fetch_token += 1
        self._fetch_href = href
        self._fetch_pending = (self._fetch_token, callback)
        self._fetch_attempts = 0
        try:
            self._fetcher_page.load(QUrl(href))
        except Exception as exc:
            log.warning("playlist fetch failed to start: %s", exc)
            self._fetch_pending = None
            callback([])

    def _on_fetcher_load_finished(self, ok: bool) -> None:
        if self._fetch_pending is None:
            return
        if not ok:
            self._deliver_fetch([])
            return
        # the SPA renders after load; probe again until track rows appear
        self._schedule_fetcher_probe(900)

    def _schedule_fetcher_probe(self, delay_ms: int) -> None:
        QTimer.singleShot(delay_ms, self._run_fetcher_probe)

    def _run_fetcher_probe(self) -> None:
        pending = self._fetch_pending
        if pending is None or pending[0] != self._fetch_token:
            return
        self._fetch_attempts += 1
        try:
            self._fetcher_page.runJavaScript(PLAYLIST_SONGS_PROBE_JS, self._on_fetcher_songs)
        except Exception as exc:
            log.warning("playlist songs probe failed: %s", exc)
            self._deliver_fetch([])
            return
        if self._fetch_attempts < 4:
            self._schedule_fetcher_probe(1600)

    def _on_fetcher_songs(self, result) -> None:
        pending = self._fetch_pending
        if pending is None or pending[0] != self._fetch_token:
            return
        songs = parse_playlist_songs_result(result)
        if songs:
            self._deliver_fetch(songs)
        elif self._fetch_attempts >= 4:
            self._deliver_fetch([])

    def _deliver_fetch(self, songs: list[dict[str, str]]) -> None:
        pending = self._fetch_pending
        if pending is None:
            return
        self._fetch_pending = None
        if self._fetch_href:
            self._playlist_song_cache[self._fetch_href] = songs
        pending[1](songs)

    def _try_play_first_song(self) -> None:
        """Click the first song of a double-clicked playlist (retried by timers)."""
        if not self._play_first_armed or self._play_first_done:
            return
        url = self.current_url()
        if self._pending_play_href and not url.startswith(self._pending_play_href.split("?")[0]):
            self._play_first_armed = False  # user navigated away; give up
            return
        try:
            self.view.page().runJavaScript(
                play_first_song_js(self.browser_page.DOCK_PX), self._on_play_first_result
            )
        except Exception as exc:
            log.warning("play-first-song failed: %s", exc)

    def _on_play_first_result(self, result) -> None:
        if result:
            self._play_first_done = True
            self._play_first_armed = False
            self.playback_diagnostics.record_player_action("playlist-play-first", str(result))

    def apply_settings(self):
        self.settings_page.apply_to(self.config_service.config)
        self.config_service.save()
        self.status_label.setText("Settings saved")
        self.stack.setCurrentWidget(self.browser_page)

    def reset_settings(self):
        self.config_service.reset()
        self.settings_page.__init__(self.config_service.config) if False else None
        # rebuild page
        idx = self.stack.indexOf(self.settings_page)
        self.stack.removeWidget(self.settings_page)
        self.settings_page = SettingsPage(self.config_service.config)
        self.settings_page.apply_btn.clicked.connect(self.apply_settings)
        self.settings_page.reset_btn.clicked.connect(self.reset_settings)
        self.stack.insertWidget(idx, self.settings_page)
        self.stack.setCurrentWidget(self.settings_page)

    def _player_js(self, action: str) -> None:
        js = player_action_js(action, self.browser_page.DOCK_PX)
        if js:
            attr = _TOGGLE_BUTTON_ATTRS.get(action)
            btn = getattr(self.player_bar, attr, None) if attr else None
            try:
                self.view.page().runJavaScript(
                    js, lambda ok, a=action, b=btn: self._on_action_result(a, ok, b)
                )
            except Exception as exc:
                log.warning("player action %s failed: %s", action, exc)

    def _on_action_result(self, action: str, ok, btn=None) -> None:
        if not ok:
            log.warning("player action %s: no matching control on page", action)
            # observable, and never a false success: the UI state comes from
            # the page probe, not from the action
            self.playback_diagnostics.record_player_action_missed(action)
            if btn is not None and btn.isCheckable():
                # the click already flipped the toggle: flip it back so a
                # missed action never leaves a stale mode lit
                btn.blockSignals(True)
                btn.setChecked(not btn.isChecked())
                btn.blockSignals(False)
            return
        # record which dispatch strategy fired (media toggle, selector,
        # or geometry fallback); playback state still comes from the
        # monitor, so this is observability, not a success claim
        self.playback_diagnostics.record_player_action(action, str(ok))

    def _set_player_volume(self, value: int) -> None:
        try:
            self.view.page().runJavaScript(volume_js(volume=max(0, min(100, value)) / 100))
        except Exception as exc:
            log.warning("volume change failed: %s", exc)

    def _set_player_muted(self, muted: bool) -> None:
        try:
            self.view.page().runJavaScript(volume_js(muted=muted))
        except Exception as exc:
            log.warning("mute toggle failed: %s", exc)

    def _apply_player_seek(self, fraction: float) -> None:
        total = float(self._last_dur)
        if total <= 0:
            log.debug("seek ignored: no track duration yet")
            return
        target = float(max(0.0, min(1.0, fraction))) * total
        try:
            self.view.page().runJavaScript(seek_js(target))
            # MPRIS clients resync from the Seeked signal; the monitor's next
            # probe confirms the actual position.
            if self.mpris is not None:
                self.mpris.emit_seeked(target)
        except Exception as exc:
            log.warning("seek failed: %s", exc)

    def current_url(self) -> str:
        return self.view.url().toString()

    def go_home(self):
        self._nav("home")

    def clear_site_data(self):
        reply = QMessageBox.question(self, "Clear site data", "This will sign you out. Continue?")
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            import shutil as _sh
            for sub in ("profile", "cache"):
                p = self.profile_manager.profile_dir / sub
                if p.exists():
                    _sh.rmtree(p, ignore_errors=True)
            self.profile_manager.ensure_dirs()
            QMessageBox.information(self, "Done", "Site data cleared. Restart the app.")
        except Exception as exc:
            log.error("clear site data failed: %s", exc)

    def _poll_now_playing(self):
        # Read-only probe of the page player state. The page DOM is never
        # modified from here (see _BrowserHost for player-bar suppression).
        # The media-event monitor is the primary state source; this probe
        # remains as the fallback (remediation spec 3.3).
        self._poll_count = (self._poll_count + 1) % 5
        try:
            self.view.page().runJavaScript(NOW_PLAYING_PROBE_JS, self._on_np_result)
            self.view.page().runJavaScript(PLAYBACK_MONITOR_JS, self._on_monitor_state)
            if self._poll_count == 0:
                # In manual-queue mode the page scrape must not replace the
                # user-queued songs; otherwise mirror the page's up-next
                # queue so the panel is never stale, visible or not.
                if not self.queue_panel.manual_queue:
                    self.view.page().runJavaScript(QUEUE_PROBE_JS, self._on_queue_result)
                self._request_playlists()
        except Exception as exc:
            log.warning("now-playing poll failed: %s", exc)
        if self.monitor.detect_stalled():
            # detect_stalled flipped the state to STALLED; the transition is
            # surfaced by _on_playback_state_changed (UI, MPRIS, diagnostics).
            pass

    def _on_monitor_state(self, result) -> None:
        payload = None
        if isinstance(result, str) and result:
            try:
                payload = json.loads(result)
            except ValueError:
                payload = None
        self.monitor.update_from_browser(payload)
        for event in self.monitor.events:
            if event.name == "encrypted" and event.timestamp > self._encrypted_noted_at:
                self._encrypted_noted_at = event.timestamp
                self.playback_diagnostics.note_encrypted_media(event.timestamp)
        # Distinguish browser-claimed PLAYING from position-confirmed
        # playback in the status line (the 1 Hz poll is the only place that
        # observes confirmation flips, which are not state transitions).
        if self.monitor.state == PlaybackState.PLAYING and not self.monitor.confirmed:
            if self.status_label.text() != "Confirming playback…":
                self.status_label.setText("Confirming playback…")
        elif self.status_label.text() == "Confirming playback…":
            self.status_label.setText("")
        # Media Session corroboration, recorded only on change so the
        # 1 Hz poll does not spam the diagnostics event log.
        session = self.monitor.media_session or {}
        ms_state = str(session.get("playbackState") or "none")
        if ms_state != self._last_media_session_state:
            self._last_media_session_state = ms_state
            self.playback_diagnostics.note_media_session(
                ms_state,
                bool(session.get("title") or session.get("artist") or session.get("album")),
            )

    def _on_queue_result(self, result):
        songs = parse_queue_result(result)
        if songs:
            # The page exposed its *real* up-next queue; that overrides the
            # locally tracked session songs until it goes away again.
            self.queue_panel.set_upcoming(songs)

    def _on_np_result(self, result):
        state = parse_probe_result(result)
        if state is None:
            return
        self._last_dur = float(state["dur"])
        title = state.get("title") or ""
        artist = state.get("artist") or ""
        playing = state["dur"] > 0 and not state["paused"]
        if state["dur"] > 0 and title:
            # Track-only feed: document.title ("Playlist - Amazon Music") and
            # other page-title junk never reach the queue panel. A song that
            # merely *loaded* (paused or not) counts — so the next playing
            # song is automatically added to the player queue as it starts.
            self.queue_panel.on_track(title, artist)
        if title and title != self._track_key:
            self._track_key = title
            self._track_title = title
            self._track_artist = artist
            self.now_playing.set_track(title)
            # a new track is being played: the pipeline restarts
            self.playback_diagnostics.note_track_selected()
            if self.mpris is not None:
                self.mpris.advance_track()
            # starting a playlist from the page queues all its songs, not
            # only the one being played
            self._maybe_queue_current_playlist()
        self.player_bar.set_state(state)
        self.now_playing.set_playing(playing)
    def _on_url_changed(self, url):
        self.status_label.setText(url.host())

    def _on_load_started(self):
        self.status_label.setText("Loading\u2026")
        # A new document invalidates media events, positions, and pipeline
        # stages gathered from the previous one; reset both so stale
        # evidence is never attributed to the new page.
        self.monitor.reset()
        try:
            self.playback_diagnostics.note_navigation(self.current_url())
        except Exception as exc:
            log.debug("navigation note failed: %s", exc)

    def _on_load_progress(self, progress):
        self.status_label.setText(f"Loading\u2026 {progress}%")

    def _on_load_finished(self, ok):
        if not ok:
            self.playback_diagnostics.note_page_loaded(url=self.current_url(), ok=False)
            self.status_label.setText("Failed to load")
            return
        self.playback_diagnostics.note_page_loaded(url=self.current_url(), ok=True)
        self.status_label.setText("")
        # Attach the read-only media-event instrumentation. Idempotent: the
        # page-side marker guard makes re-injection a no-op, and the SPA's
        # own re-navigations wipe it, so every load re-attaches.
        try:
            self.view.page().runJavaScript(PLAYBACK_MONITOR_JS, self._on_monitor_state)
        except Exception as exc:
            log.warning("playback instrumentation failed: %s", exc)
        if "playlists" in self.current_url():
            # playlists index loaded: scrape the playlist cards into the
            # sidebar list (the SPA renders after loadFinished)
            for delay in (1500, 4000, 8000):
                QTimer.singleShot(delay, self._request_playlists)
        if self._play_first_armed and not self._play_first_done:
            # a playlist was double-clicked: start its first song once the
            # page has rendered (a few retries; a no-op once one attempt
            # lands)
            for delay in (1200, 2800, 5500):
                QTimer.singleShot(delay, self._try_play_first_song)

    def _on_playback_state_changed(self, state) -> None:
        playing = state == PlaybackState.PLAYING
        self.now_playing.set_playing(playing)
        if self.mpris is not None:
            self.mpris.update_playback()
        diagnostics = self.playback_diagnostics
        if state == PlaybackState.ERROR:
            diagnostics.record_media_error(self.monitor.last_error or "playback failed")
            self.status_label.setText("Playback failed")
        elif state == PlaybackState.STALLED:
            diagnostics.classify("playback stopped progressing")
            self.status_label.setText("Playback stalled")
        elif playing and self.monitor.duration > 0:
            # The page fired 'playing' with a known duration: the decoder is
            # running, which verifies media_decoding_started. audio_output is
            # verified only once the position actually advances — a stream
            # stuck at 0:00 decodes nothing audible.
            diagnostics.note_media_decoding()
            if self.monitor.position > 0:
                diagnostics.note_audio_output()

    def _on_render_terminated(self, status, code):
        self.playback_diagnostics.record_renderer_termination(status, code)
        log.error("render process terminated: status=%s code=%s", status, code)
        QMessageBox.warning(self, "Renderer error", "Renderer stopped. Reloading.")
        self.view.reload()

    def _on_download_requested(self, download):
        suggested = safe_filename(download.downloadFileName())
        dest_dir = default_download_dir()
        reply = QMessageBox.question(self, "Download file", f"Download {suggested} to {dest_dir}?")
        if reply != QMessageBox.StandardButton.Yes:
            download.cancel()
            return
        target = validate_destination(dest_dir, suggested)
        if target is None:
            download.cancel()
            return
        download.setDownloadDirectory(str(target.parent))
        download.setDownloadFileName(target.name)
        download.accept()

    def _setup_shortcuts(self):
        shortcuts = {
            "Ctrl+R": self.view.reload,
            "Alt+Left": self.view.back,
            "Alt+Right": self.view.forward,
            "Ctrl+H": self.go_home,
            "Ctrl+,": self.show_settings,
            "Ctrl+Q": self.close,
        }
        for seq, slot in shortcuts.items():
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(slot)
        # media keys are safe: they cannot hijack typing in the page
        for key, action in (
            (Qt.Key.Key_MediaPlay, "play"),
            (Qt.Key.Key_MediaPause, "play"),
            (Qt.Key.Key_MediaTogglePlayPause, "play"),
            (Qt.Key.Key_MediaNext, "next"),
            (Qt.Key.Key_MediaPrevious, "previous"),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda _checked=False, a=action: self._player_js(a))

    def _setup_tray(self):
        self.tray = None
        cfg = self.config_service.config
        if not cfg.tray_enabled or not tray_available():
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu()
        show_act = menu.addAction("Show"); show_act.triggered.connect(self.show_and_raise)
        hide_act = menu.addAction("Hide"); hide_act.triggered.connect(self.hide)
        menu.addSeparator()
        # transport controls: the same page-player actions as the native bar
        prev_act = menu.addAction("Previous track")
        prev_act.triggered.connect(lambda: self._player_js("previous"))
        play_act = menu.addAction("Play/Stop")
        play_act.triggered.connect(lambda: self._player_js("play"))
        next_act = menu.addAction("Next track")
        next_act.triggered.connect(lambda: self._player_js("next"))
        menu.addSeparator()
        home_act = menu.addAction("Home"); home_act.triggered.connect(self.go_home)
        settings_act = menu.addAction("Settings"); settings_act.triggered.connect(self.show_settings)
        menu.addSeparator()
        quit_act = menu.addAction("Quit"); quit_act.triggered.connect(QApplication.instance().quit)
        from PySide6.QtGui import QIcon
        icon = self.windowIcon() if not self.windowIcon().isNull() else QIcon()
        self.tray = create_tray(icon, menu)
        if self.tray is not None:
            self.tray.activated.connect(lambda r: self.show_and_raise() if r == 2 else None)

    def show_and_raise(self):
        self.show(); self.raise_(); self.activateWindow()

    def closeEvent(self, event):
        cfg = self.config_service.config
        if cfg.minimize_to_tray and self.tray is not None:
            event.ignore()
            self.hide()
            if self.tray is not None:
                from PySide6.QtWidgets import QSystemTrayIcon
                self.tray.showMessage("Amazon Music Desktop", "Running in background", QSystemTrayIcon.MessageIcon.Information, 2000)
            return
        super().closeEvent(event)
