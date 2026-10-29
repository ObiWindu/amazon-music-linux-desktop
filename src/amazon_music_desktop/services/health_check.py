"""Environment and dependency health checks."""

from __future__ import annotations

import platform
from typing import Any

from .configuration import CONFIG_DIR, PROFILE_DIR


def collect_health() -> dict[str, Any]:
    import PySide6
    from PySide6.QtCore import qVersion
    info: dict[str, Any] = {}
    info["architecture"] = platform.machine()
    info["python"] = platform.python_version()
    info["pyside6"] = PySide6.__version__
    info["qt"] = qVersion()
    info["config_dir"] = str(CONFIG_DIR)
    info["profile_dir"] = str(PROFILE_DIR)
    return info
