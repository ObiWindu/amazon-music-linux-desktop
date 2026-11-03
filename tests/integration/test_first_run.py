"""Clean-install (first-run) lifecycle: a fresh HOME gets working dirs,
CDM links, and the engine flag through the same calls app.main() makes.
No Qt objects are constructed; the developer's real HOME is untouched.
"""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path


def _elf_bytes(machine: int) -> bytes:
    return b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 10 + struct.pack("<H", machine)


def test_first_run_provisions_profile_cdm_and_flag(tmp_path, monkeypatch):
    import amazon_music_desktop.browser.drm_diagnostics as d
    from amazon_music_desktop.browser.profile import ProfileManager

    home = tmp_path / "home"
    system = tmp_path / "system" / "libwidevinecdm.so"
    system.parent.mkdir(parents=True)
    system.write_bytes(_elf_bytes(183) + b"\x00" * 64)
    (tmp_path / "system" / "manifest.json").write_text(json.dumps({"version": "4.10.2662.3"}))

    monkeypatch.setattr(d, "CDM_PATH", system)
    monkeypatch.setattr(d, "WIDEVINE_CDM_DIR", tmp_path / "system" / "WidevineCdm")
    monkeypatch.setattr(d, "BUNDLED_CDM_DIRS", ())
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    monkeypatch.setattr(d.platform, "machine", lambda: "aarch64")
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)

    # 1. profile + cache dirs with restrictive permissions
    pm = ProfileManager(profile_dir=home / ".local" / "share" / "test-app")
    pm.ensure_dirs()
    for sub in ("profile", "cache"):
        mode = (home / ".local" / "share" / "test-app" / sub).stat().st_mode & 0o777
        assert mode == 0o700

    # 2. user-level CDM lookup dirs populated for the engine
    d.ensure_widevine_user_dir()
    for base in ("chromium", "google-chrome"):
        for platform_dir in ("linux_arm64", "linux_x64"):
            link = (
                home / ".config" / base / "WidevineCdm"
                / "_platform_specific" / platform_dir / "libwidevinecdm.so"
            )
            assert link.is_symlink(), f"missing engine lookup link {link}"
            assert link.resolve() == system.resolve()

    # 3. engine flag set before QtWebEngine init (user-level component
    # build outranks the system file by design)
    expected = (
        home / ".config" / "chromium" / "WidevineCdm" / "_platform_specific"
        / "linux_arm64" / "libwidevinecdm.so"
    )
    assert d.configure_widevine() == expected
    assert f"--widevine-cdm-path={expected}" in os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]


def test_packaging_metadata_consistent():
    """Spec version matches pyproject; installed files exist in the repo."""
    import re

    root = Path(__file__).resolve().parents[2]
    spec = (root / "packaging" / "rpm" / "amazon-music-desktop.spec").read_text()
    spec_version = re.search(r"^Version:\s*(\S+)", spec, re.MULTILINE).group(1)
    pyproject = (root / "pyproject.toml").read_text()
    assert f'version = "{spec_version}"' in pyproject
    for rel in (
        "packaging/desktop/amazon-music-desktop.desktop",
        "packaging/icons/app.png",
        "src/amazon_music_desktop/__main__.py",
    ):
        assert (root / rel).exists(), f"packaging input missing: {rel}"
