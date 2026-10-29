"""Desktop integration: tray icon, shortcuts registration helpers."""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def tray_available() -> bool:
    return QSystemTrayIcon.isSystemTrayAvailable()


def create_tray(icon: QIcon, menu: QMenu) -> QSystemTrayIcon | None:
    if not tray_available():
        return None
    tray = QSystemTrayIcon(icon)
    tray.setContextMenu(menu)
    tray.setToolTip("Amazon Music Desktop")
    tray.show()
    return tray
