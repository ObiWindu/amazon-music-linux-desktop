"""WebEngine profile and persistent storage management."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWebEngineCore import QWebEngineProfile

from ..services.configuration import PROFILE_DIR
from ..services.logging_service import get_logger

log = get_logger("profile")


class ProfileManager:
    def __init__(self, profile_dir: Path = PROFILE_DIR):
        self.profile_dir = profile_dir
        self.profile_path = profile_dir / "profile"
        self.cache_path = profile_dir / "cache"
        self._profile: QWebEngineProfile | None = None

    def ensure_dirs(self) -> None:
        for d in (self.profile_dir, self.profile_path, self.cache_path):
            d.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(d, 0o700)
            except OSError as exc:
                log.warning("could not chmod %s: %s", d, exc)

    def create_profile(self, off_the_record: bool = False) -> QWebEngineProfile:
        self.ensure_dirs()
        if off_the_record:
            profile = QWebEngineProfile()
            log.info("created off-the-record profile")
            self._profile = profile
            return profile
        profile = QWebEngineProfile("amazon-music-desktop")
        profile.setPersistentStoragePath(str(self.profile_path))
        profile.setCachePath(str(self.cache_path))
        # keep http cache on disk
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )
        # Architecture-aware UA: Amazon serves different builds per arch and
        # the Widevine VMP check covers the execution environment, so the UA
        # must never claim an architecture we are not running on.
        import platform as _platform

        _machine = _platform.machine().lower()
        _ua_arch = "aarch64" if _machine in ("aarch64", "arm64") else "x86_64"
        profile.setHttpUserAgent(
            f"Mozilla/5.0 (X11; Linux {_ua_arch}) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        )
        log.info("created persistent profile at %s", self.profile_path)
        self._profile = profile
        return profile

    @property
    def profile(self) -> QWebEngineProfile | None:
        return self._profile

    def profile_permissions_ok(self) -> bool:
        try:
            st = self.profile_path.stat()
            return (st.st_mode & 0o777) == 0o700
        except OSError:
            return False
