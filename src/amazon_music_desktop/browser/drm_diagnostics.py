"""Widevine / DRM diagnostic helpers."""

from __future__ import annotations

import os
import platform
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..services.logging_service import get_logger

log = get_logger("drm")

CDM_PATH = Path("/var/lib/widevine/libwidevinecdm.so")
WIDEVINE_CDM_DIR = Path("/var/lib/widevine/WidevineCdm")


@dataclass
class StageResult:
    stage: str
    ok: bool
    details: dict[str, Any]
    error: str | None = None


def check_library_presence(cdm_path: Path = CDM_PATH) -> StageResult:
    details: dict[str, Any] = {"path": str(cdm_path)}
    if not cdm_path.exists():
        return StageResult("A_library_presence", False, details, "CDM file does not exist")
    if not os.access(cdm_path, os.R_OK):
        return StageResult("A_library_presence", False, details, "CDM not readable")
    try:
        st = cdm_path.stat()
        details["size"] = st.st_size
        details["mode"] = oct(st.st_mode & 0o777)
    except OSError as exc:
        return StageResult("A_library_presence", False, details, str(exc))
    # ELF arch
    arch = _elf_arch(cdm_path)
    details["arch"] = arch
    if arch != "aarch64":
        return StageResult("A_library_presence", False, details, f"unexpected architecture: {arch}")
    # deps
    deps_ok, deps_out = _ldd(cdm_path)
    details["deps_ok"] = deps_ok
    details["deps_output"] = deps_out
    if not deps_ok:
        return StageResult("A_library_presence", False, details, "unresolved dependencies")
    return StageResult("A_library_presence", True, details)


def _elf_arch(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
            if magic != b"\x7fELF":
                return "not-elf"
            f.seek(18)
            e_machine = struct.unpack("<H", f.read(2))[0]
        # 183 = EM_AARCH64
        if e_machine == 183:
            return "aarch64"
        if e_machine == 62:
            return "x86_64"
        return f"unknown({e_machine})"
    except Exception as exc:
        return f"error:{exc}"


def _ldd(path: Path) -> tuple[bool, str]:
    try:
        proc = subprocess.run(["ldd", str(path)], capture_output=True, text=True, timeout=30, check=False)
        out = (proc.stdout + proc.stderr).strip()
        # detect "not found"
        if "not found" in out.lower():
            return False, out
        if proc.returncode != 0:
            return False, out
        return True, out
    except Exception as exc:
        return False, str(exc)


def browser_info() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "fedora": _fedora_release(),
        "pyside6": _pyside_version(),
        "qt": _qt_version(),
        "chromium_ua_hint": "QtWebEngine/6.11.2 Chrome/140.0.0.0",
    }


def _fedora_release() -> str:
    try:
        data = Path("/etc/os-release").read_text()
        for line in data.splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return "unknown"


def _pyside_version() -> str:
    try:
        import PySide6
        return PySide6.__version__
    except Exception:
        return "unavailable"


def _qt_version() -> str:
    try:
        from PySide6.QtCore import qVersion
        return qVersion()
    except Exception:
        return "unavailable"


def ensure_widevine_user_dir() -> None:
    """Ensure a user-level WidevineCdm directory exists pointing at system CDM."""
    home = Path.home()
    for base in (home / ".config" / "chromium", home / ".config" / "google-chrome"):
        target = base / "WidevineCdm"
        if target.exists():
            continue
        try:
            target.mkdir(parents=True, exist_ok=True)
            sub = target / "_platform_specific" / "linux_x64"
            sub.mkdir(parents=True, exist_ok=True)
            manifest_src = Path("/var/lib/widevine/WidevineCdm/manifest.json")
            if not (target / "manifest.json").exists():
                import json
                manifest = {}
                if manifest_src.exists():
                    try:
                        manifest = json.loads(manifest_src.read_text())
                    except Exception:
                        manifest = {}
                # add linux platform entry so Qt/Chromium can discover the CDM
                platforms = manifest.setdefault("platforms", [])
                if not any(p.get("os") == "linux" for p in platforms):
                    platforms.append({"os": "linux", "arch": "x64", "sub_package_path": "_platform_specific/linux_x64/"})
                (target / "manifest.json").write_text(json.dumps(manifest, indent=2))
            link = sub / "libwidevinecdm.so"
            if not link.exists():
                try:
                    link.symlink_to("/var/lib/widevine/libwidevinecdm.so")
                except OSError:
                    pass
        except OSError as exc:
            log.debug("could not prepare widevine dir %s: %s", target, exc)


def run_stage_a() -> StageResult:
    return check_library_presence()


def format_stage(result: StageResult) -> str:
    lines = [f"[{result.stage}] {'OK' if result.ok else 'FAIL'}"]
    if result.error:
        lines.append(f"  error: {result.error}")
    for k, v in result.details.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)
