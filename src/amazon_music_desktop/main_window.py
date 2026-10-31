"""Main application window (Amazon Music-like shell)."""

from __future__ import annotations

import json
import subprocess
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
        "border-radius: 8px; color: #cdd6f4; background: transparent; font-size: 13px; }"
        "QPushButton:hover { background: #313244; }"
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
        sidebar.setStyleSheet("background: #181825; border-right: 1px solid #313244;")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(10, 16, 10, 16)
        sb_layout.setSpacing(4)

        title = QLabel("Amazon Music")
        title.setStyleSheet("color: #cba6f7; font-size: 16px; font-weight: bold; padding: 8px;")
        sb_layout.addWidget(title)

        self.now_playing = NowPlayingWidget()
        sb_layout.addWidget(self.now_playing)

        self.btn_home = _sidebar_button("🏠  Home", "Home")
        self.btn_search = _sidebar_button("🔍  Search", "Search")
        self.btn_library = _sidebar_button("📚  Library", "Library")
        self.btn_playlists = _sidebar_button("🎵  Playlists", "Playlists")
        self.btn_favorites = _sidebar_button("❤  Favorites", "Favorites")
        for b in (self.btn_home, self.btn_search, self.btn_library, self.btn_playlists, self.btn_favorites):
            sb_layout.addWidget(b)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #a6adc8; font-size: 11px; padding: 4px 8px;")
        self.status_label.setWordWrap(True)
        sb_layout.addWidget(self.status_label)

        sb_layout.addStretch()

        self.btn_settings = _sidebar_button("⚙  Settings", "Settings")
        self.btn_diagnostics = _sidebar_button("🩺  Diagnostics", "Diagnostics")
        self.btn_queue = _sidebar_button("📋  Queue", "Queue")
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
        self.btn_playlists.clicked.connect(lambda: self._nav("playlists"))
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
        self.view.load(QUrl(url))
        self._set_active({
            "home": self.btn_home, "search": self.btn_search, "library": self.btn_library,
            "playlists": self.btn_playlists, "favorites": self.btn_favorites,
        }[section])
        self.stack.setCurrentWidget(self.browser_page)

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
            try:
                self.view.page().runJavaScript(
                    js, lambda ok, a=action: self._on_action_result(a, ok)
                )
            except Exception as exc:
                log.warning("player action %s failed: %s", action, exc)

    def _on_action_result(self, action: str, ok) -> None:
        if not ok:
            log.warning("player action %s: no matching control on page", action)
            # observable, and never a false success: the UI state comes from
            # the page probe, not from the action
            self.playback_diagnostics.record_player_action_missed(action)

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
        try:
            self.view.page().runJavaScript(seek_js(float(max(0.0, min(1.0, fraction))) * total))
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
            if self._poll_count == 0 and self.queue_panel.list.isVisible():
                self.view.page().runJavaScript(QUEUE_PROBE_JS, self._on_queue_result)
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
            # merely *loaded* (paused or not) counts.
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
        self.player_bar.set_state(state)
        self.now_playing.set_playing(playing)
    def _on_url_changed(self, url):
        self.status_label.setText(url.host())

    def _on_load_started(self):
        self.status_label.setText("Loading\u2026")

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
            # The page fired 'playing': audio is actually being produced,
            # which is direct evidence for the two final pipeline stages.
            diagnostics.note_media_decoding()
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
