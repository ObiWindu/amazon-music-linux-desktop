"""Main application window (Amazon Music-like shell)."""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QSize, QUrl
from PySide6.QtGui import QKeySequence
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .browser.download_policy import default_download_dir, safe_filename, validate_destination
from .browser.navigation import NavigationDecision, NavigationPolicy
from .browser.profile import ProfileManager
from .services.configuration import ConfigService
from .services.desktop_integration import create_tray, tray_available
from .services.logging_service import get_logger
from .ui.now_playing import NowPlayingWidget
from .ui.settings_page import SettingsPage

log = get_logger("main_window")


class WebPage(QWebEnginePage):
    def __init__(self, profile, policy, parent=None):
        super().__init__(profile, parent)
        self.policy = policy

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


class MainWindow(QMainWindow):
    def __init__(self, config_service: ConfigService, profile_manager: ProfileManager, profile, parent=None):
        super().__init__(parent)
        self.config_service = config_service
        self.profile_manager = profile_manager
        self.profile = profile
        self.policy = NavigationPolicy()

        self.setWindowTitle("Amazon Music Desktop")
        self.setMinimumSize(QSize(1000, 640))

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

        # browser page
        self.browser_page = QWidget()
        bp = QVBoxLayout(self.browser_page)
        bp.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView()
        self.page = WebPage(self.profile, self.policy, self.view)
        self.view.setPage(self.page)
        bp.addWidget(self.view, 1)
        self.stack.addWidget(self.browser_page)

        # settings page
        self.settings_page = SettingsPage(self.config_service.config)
        self.stack.addWidget(self.settings_page)

        # bottom bar
        bottom = QFrame()
        bottom.setFixedHeight(96)
        bottom.setStyleSheet("background: #181825; border-top: 1px solid #313244;")
        bv = QVBoxLayout(bottom)
        bv.setContentsMargins(12, 6, 12, 6)
        bv.setSpacing(4)

        # top row: player controls
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self.shuffle_btn = QPushButton("🔀")
        self.prev_btn = QPushButton("⏮")
        self.play_btn = QPushButton("▶")
        self.next_btn = QPushButton("⏭")
        self.repeat_btn = QPushButton("🔁")
        for b in (self.shuffle_btn, self.repeat_btn):
            b.setStyleSheet("background: transparent; border: none; color: #cdd6f4;")
        for b in (self.shuffle_btn, self.prev_btn, self.play_btn, self.next_btn, self.repeat_btn):
            b.setFixedWidth(40)
        top_row.addWidget(self.shuffle_btn)
        top_row.addWidget(self.prev_btn)
        top_row.addWidget(self.play_btn)
        top_row.addWidget(self.next_btn)
        top_row.addWidget(self.repeat_btn)

        top_row.addSpacing(12)
        self.back_btn = QPushButton("◀")
        self.forward_btn = QPushButton("▶")
        self.reload_btn = QPushButton("⟳")
        for b in (self.back_btn, self.forward_btn, self.reload_btn):
            b.setFixedWidth(40)
        top_row.addWidget(self.back_btn)
        top_row.addWidget(self.forward_btn)
        top_row.addWidget(self.reload_btn)

        self.track_label = QLabel("Amazon Music")
        self.track_label.setStyleSheet("color: #cdd6f4; font-size: 13px;")
        top_row.addWidget(self.track_label, 1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        top_row.addWidget(self.status_label)

        bv.addLayout(top_row)

        # bottom row: full-width progress bar
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMinimumHeight(8)
        bv.addWidget(self.progress)

        # place bottom bar below central content
        # restructure: use a vertical layout containing stack+bottom
        # Rebuild central properly
        central.deleteLater()
        central2 = QWidget(self)
        self.setCentralWidget(central2)
        outer_layout = QVBoxLayout(central2)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        # top row: sidebar + stack
        top_row = QWidget()
        tr = QHBoxLayout(top_row)
        tr.setContentsMargins(0, 0, 0, 0)
        tr.setSpacing(0)
        tr.addWidget(sidebar)
        tr.addWidget(self.stack, 1)

        # right queue panel
        self.queue_panel = QFrame()
        self.queue_panel.setFixedWidth(260)
        self.queue_panel.setStyleSheet("background: #181825; border-left: 1px solid #313244;")
        qp = QVBoxLayout(self.queue_panel)
        qp.setContentsMargins(10, 16, 10, 16)
        qtitle = QLabel("Queue")
        qtitle.setStyleSheet("color: #cba6f7; font-size: 16px; font-weight: bold;")
        qp.addWidget(qtitle)
        from PySide6.QtWidgets import QListWidget
        self.queue_list = QListWidget()
        self.queue_list.setStyleSheet("background: #1e1e2e; color: #cdd6f4; border: none;")
        qp.addWidget(self.queue_list, 1)
        tr.addWidget(self.queue_panel)

        outer_layout.addWidget(top_row, 1)
        outer_layout.addWidget(bottom)

        # web settings
        ws = self.page.settings()
        ws.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        ws.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)

        # signals
        self.view.urlChanged.connect(self._on_url_changed)

        from PySide6.QtCore import QTimer
        self._np_timer = QTimer(self)
        self._np_timer.timeout.connect(self._poll_now_playing)
        self._np_timer.start(4000)
        self.view.loadStarted.connect(self._on_load_started)
        self.view.loadProgress.connect(self._on_load_progress)
        self.view.loadFinished.connect(self._on_load_finished)
        self.page.renderProcessTerminated.connect(self._on_render_terminated)
        self.profile.downloadRequested.connect(self._on_download_requested)

        # wire
        self.back_btn.clicked.connect(self.view.back)
        self.forward_btn.clicked.connect(self.view.forward)
        self.reload_btn.clicked.connect(self.view.reload)
        self.prev_btn.clicked.connect(lambda: self._player_js("previous"))
        self.play_btn.clicked.connect(lambda: self._player_js("play"))
        self.next_btn.clicked.connect(lambda: self._player_js("next"))
        self.shuffle_btn.clicked.connect(lambda: self._player_js("shuffle"))
        self.repeat_btn.clicked.connect(lambda: self._player_js("repeat"))
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
        DiagnosticsDialog(self).exec()

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
        js = {
            "previous": "document.querySelector('[aria-label*=\"Previous\"]')?.click();",
            "play": "document.querySelector('[aria-label*=\"Play\"],[aria-label*=\"Pause\"]')?.click();",
            "next": "document.querySelector('[aria-label*=\"Next\"]')?.click();",
            "shuffle": "document.querySelector('[aria-label*=\"Shuffle\"]')?.click();",
            "repeat": "document.querySelector('[aria-label*=\"Repeat\"]')?.click();",
        }.get(action, "")
        if js:
            self.view.page().runJavaScript(js)

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
        js = "document.title"
        try:
            self.view.page().runJavaScript(js, self._on_np_result)
        except Exception:
            pass

    def _on_np_result(self, result):
        if isinstance(result, str) and result:
            self.now_playing.set_track(result)
            if self.queue_list.count() == 0 or self.queue_list.item(self.queue_list.count() - 1).text() != result:
                self.queue_list.addItem(result)

    def _on_url_changed(self, url):
        self.back_btn.setEnabled(self.view.history().canGoBack())
        self.forward_btn.setEnabled(self.view.history().canGoForward())
        self.status_label.setText(url.host())

    def _on_load_started(self):
        self.progress.setValue(0)

    def _on_load_progress(self, progress):
        self.progress.setValue(progress)

    def _on_load_finished(self, ok):
        self.progress.setValue(100 if ok else 0)
        if not ok:
            self.status_label.setText("Failed to load")

    def _on_render_terminated(self, status, code):
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
        from PySide6.QtGui import QShortcut
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
