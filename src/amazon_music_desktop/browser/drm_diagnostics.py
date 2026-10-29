"""Widevine / DRM diagnostic helpers."""

from __future__ import annotations

import json
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
WIDEVINE_CDM_FLAG = "--widevine-cdm-path"

# JS probe: goes one step beyond key-system detection by creating MediaKeys
# and a MediaKeySession, which forces Chromium to instantiate the CDM.
# Success => CDM loads. Failure here (while key-system detection passes)
# => CDM rejected/incompatible. License failures happen later, server-side.
# NOTE: QtWebEngine does not resolve returned Promises to Python callbacks,
# so callers must store the result (e.g. on window) and read it back later.
CDM_SESSION_PROBE_JS = (
    "window.__amdCdmTest = {ok: false, error: 'probe started, no result yet'};"
    "(async () => {"
    "try {"
    "window.__amdCdmTest = {ok: false, error: 'stage: requesting key system...'};"
    "const access = await navigator.requestMediaKeySystemAccess("
    "'com.widevine.alpha', [{"
    "initDataTypes: ['cenc'],"
    "audioCapabilities: [{contentType: 'audio/mp4; codecs=\"mp4a.40.2\"'}],"
    "videoCapabilities: [{contentType: 'video/mp4; codecs=\"avc1.42E01E\"'}]"
    "}]);"
    "window.__amdCdmTest = {ok: false, error: 'stage: creating MediaKeys...'};"
    "const keys = await access.createMediaKeys();"
    "window.__amdCdmTest = {ok: false, error: 'stage: creating session...'};"
    "const session = keys.createSession();"
    "if (!session) throw new Error('createSession returned null');"
    "window.__amdCdmTest = {ok: true, keySystem: access.keySystem};"
    "} catch (e) { window.__amdCdmTest = {ok: false, error: (e && e.name ? e.name + ': ' : '') + (e && e.message ? e.message : e)}; }"
    "})();"
    "'started';"
)

# Read-back for the CDM session probe. QtWebEngine 6.11 delivers only
# primitive values from runJavaScript (objects, arrays and undefined all
# arrive as the empty string), so the read-back stringifies and uses the
# 'MISSING' sentinel for an absent marker.
CDM_TEST_READ_JS = "(JSON.stringify(window.__amdCdmTest) || 'MISSING')"


def cdm_probe_state(result: object) -> tuple[str, object]:
    """Classify a read-back of the CDM session probe marker.

    Returns (state, raw) where state is one of:
    - "missing":  marker absent (page reloaded or probe never ran)
    - "progress": probe is mid-flight (raw carries the current stage)
    - "final":    probe finished (raw is the result dict or unexpected value)
    """
    if result is None or result == "" or result == "MISSING":
        return "missing", None
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return "final", result
    if isinstance(result, dict):
        if result.get("ok") is True:
            return "final", result
        if str(result.get("error", "")).startswith("stage:"):
            return "progress", result
        return "final", result
    return "final", result


def parse_cdm_session_result(result: object) -> StageResult:
    """Normalize the CDM session probe callback payload."""
    if isinstance(result, dict) and result.get("ok") is True:
        return StageResult(
            "C_cdm_session", True, {"keySystem": result.get("keySystem", "?")}
        )
    error = "no result"
    if isinstance(result, dict):
        error = str(result.get("error", "unknown"))
    return StageResult("C_cdm_session", False, {}, error)


def cdm_version(cdm: Path | None = None) -> str:
    """Read the CDM version from the neighboring manifest.json."""
    base = cdm or CDM_PATH
    for manifest in (
        base.parent / "manifest.json",
        WIDEVINE_CDM_DIR / "manifest.json",
        Path.home() / ".config" / "chromium" / "WidevineCdm" / "manifest.json",
    ):
        try:
            if manifest.exists():
                import json

                data = json.loads(manifest.read_text())
                if isinstance(data.get("version"), str):
                    return data["version"]
        except Exception as exc:
            log.debug("could not read %s: %s", manifest, exc)
            continue
    return "unknown"


def _user_cdm_candidates() -> list[Path]:
    home = Path.home()
    return [
        home / ".config" / "chromium" / "WidevineCdm" / "_platform_specific" / "linux_x64" / "libwidevinecdm.so",
        home / ".config" / "google-chrome" / "WidevineCdm" / "_platform_specific" / "linux_x64" / "libwidevinecdm.so",
    ]


def find_usable_cdm() -> Path | None:
    """Return the first readable CDM library, system install preferred."""
    for cand in [CDM_PATH, *_user_cdm_candidates()]:
        try:
            if cand.exists() and os.access(cand, os.R_OK) and cand.stat().st_size > 0:
                return cand
        except OSError:
            continue
    return None


def build_widevine_flags(cdm: Path | None, existing: str = "") -> str:
    """Append the Widevine CDM flag if a CDM exists and no flag is set yet."""
    if WIDEVINE_CDM_FLAG in existing:
        return existing.strip()
    if cdm is None:
        return existing.strip()
    flag = f"{WIDEVINE_CDM_FLAG}={cdm}"
    return f"{existing} {flag}".strip() if existing.strip() else flag


def configure_widevine() -> Path | None:
    """Point QtWebEngine at the Widevine CDM before it initializes.

    Must run before QApplication is constructed (Chromium reads
    QTWEBENGINE_CHROMIUM_FLAGS at engine init). Returns the CDM in use.
    """
    cdm = find_usable_cdm()
    current = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    updated = build_widevine_flags(cdm, current)
    if updated != current:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = updated
    if cdm is None:
        log.warning("no usable Widevine CDM found; protected playback will fail")
    else:
        log.info("using Widevine CDM at %s", cdm)
    return cdm


def detect_freeworld() -> bool | None:
    """Check for the Fedora freeworld codec library (libavcodec-freeworld).

    On Fedora the freeworld codec stack ships as ``libavcodec-freeworld``
    from RPM Fusion free — there is no qt6-qtwebengine-freeworld build for
    Fedora. Returns True/False on rpm systems, None when rpm is unavailable.
    """
    try:
        proc = subprocess.run(
            ["rpm", "-q", "libavcodec-freeworld"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except Exception:
        return None
    return proc.returncode == 0


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
