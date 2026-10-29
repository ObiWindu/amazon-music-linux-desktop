"""Application startup and shutdown."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .browser.drm_diagnostics import configure_widevine, detect_freeworld, ensure_widevine_user_dir
from .browser.profile import ProfileManager
from .main_window import MainWindow
from .services.configuration import ConfigService, ensure_dirs
from .services.logging_service import get_logger, setup_logging


def _setup_high_dpi() -> None:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    _setup_high_dpi()

    config_service = ConfigService()
    config = config_service.load()
    setup_logging(config.diagnostics_verbosity)
    log = get_logger("app")
    log.info("starting Amazon Music Desktop")

    ensure_dirs()
    ensure_widevine_user_dir()
    cdm = configure_widevine()
    if cdm is None:
        log.warning("starting without Widevine CDM: protected playback will fail")
    freeworld = detect_freeworld()
    if freeworld is False:
        log.warning(
            "qt6-qtwebengine-freeworld is not installed; stock Fedora WebEngine "
            "lacks proprietary codecs required for protected playback"
        )

    app = QApplication(argv)
    app.setApplicationName("Amazon Music Desktop")
    # load stylesheet
    qss = Path(__file__).resolve().parent / "resources" / "styles" / "app.qss"
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))
    app.setApplicationDisplayName("Amazon Music Desktop")
    app.setOrganizationName("Aurora")
    app.setOrganizationDomain("amazon-music-desktop.local")

    # icon
    icon_path = Path(__file__).resolve().parent / "resources" / "icons" / "app.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    profile_manager = ProfileManager()
    profile = profile_manager.create_profile()

    window = MainWindow(config_service, profile_manager, profile)
    window.show()

    # restore geometry not stored in config beyond size
    window.resize(config.window_width, config.window_height)
    if config.window_x is not None and config.window_y is not None:
        window.move(config.window_x, config.window_y)

    # handle clean shutdown: save config on quit
    def on_quit():
        try:
            cfg = config_service.config
            cfg.window_width = window.width()
            cfg.window_height = window.height()
            cfg.window_x = window.x()
            cfg.window_y = window.y()
            cfg.last_url = window.current_url()
            config_service.save()
        except Exception as exc:
            log.warning("config save on quit failed: %s", exc)
    app.aboutToQuit.connect(on_quit)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
