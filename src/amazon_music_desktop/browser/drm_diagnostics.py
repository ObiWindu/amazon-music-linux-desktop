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

# Optional CDM installed by an RPM built with --define 'bundled_cdm ...'.
# Keep both libdir spellings so the same package layout works on Fedora
# (/usr/lib64) and Debian-style systems (/usr/lib).
BUNDLED_CDM_DIRS: tuple[Path, ...] = (
    Path("/usr/lib64/amazon-music-desktop/WidevineCdm"),
    Path("/usr/lib/amazon-music-desktop/WidevineCdm"),
)

# Chromium's component-updated Widevine CDM lives under
# <profile>/WidevineCdm/<version>/_platform_specific/<platform>/.
# Older installs (and Qt's linux_x64 workaround) use an unversioned
# WidevineCdm/_platform_specific/<platform>/ directory instead.
_PLATFORM_DIRS: dict[str, tuple[str, ...]] = {
    "aarch64": ("linux_arm64", "linux_x64"),
    "arm64": ("linux_arm64", "linux_x64"),
    "x86_64": ("linux_x64", "linux_arm64"),
    "amd64": ("linux_x64", "linux_arm64"),
}

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


def _host_elf_arch() -> str | None:
    machine = platform.machine().lower()
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    return None


def _platform_dirs() -> tuple[str, ...]:
    return _PLATFORM_DIRS.get(platform.machine().lower(), ("linux_arm64", "linux_x64"))


def _manifest_for(cdm: Path) -> dict[str, Any]:
    """Return the Widevine manifest next to *cdm*, if one can be read."""
    for parent in (cdm.parent, cdm.parent.parent, cdm.parent.parent.parent):
        manifest = parent / "manifest.json"
        try:
            if manifest.is_file():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except (OSError, ValueError):
            continue
    return {}


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def cdm_version(cdm: Path | None = None) -> str:
    """Read the CDM version from the manifest next to the selected library."""
    base = cdm or find_usable_cdm() or CDM_PATH
    version = _manifest_for(base).get("version")
    return version if isinstance(version, str) and version else "unknown"


def _widevine_roots() -> list[Path]:
    """Return system and per-application WidevineCdm directories."""
    home = Path.home()
    roots: list[Path] = [WIDEVINE_CDM_DIR, *BUNDLED_CDM_DIRS]
    for base in (home / ".config", home / ".local" / "share"):
        try:
            roots.extend(sorted(base.glob("*/WidevineCdm")))
        except OSError:
            continue
    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        try:
            key = str(root.resolve())
        except OSError:
            key = str(root)
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _candidate_paths() -> list[Path]:
    """Enumerate plausible CDM library locations, including versioned ones."""
    paths: list[Path] = [CDM_PATH]
    for root in _widevine_roots():
        for platform_dir in _platform_dirs():
            paths.append(root / "_platform_specific" / platform_dir / "libwidevinecdm.so")
        try:
            children = sorted(
                child
                for child in root.iterdir()
                if child.is_dir() and not child.is_symlink() and not child.name.startswith("_")
            )
        except OSError:
            children = []
        for child in children:
            for platform_dir in _platform_dirs():
                paths.append(child / "_platform_specific" / platform_dir / "libwidevinecdm.so")
                nested = child / "WidevineCdm"
                if nested.is_dir():
                    paths.append(nested / "_platform_specific" / platform_dir / "libwidevinecdm.so")
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def find_usable_cdm() -> Path | None:
    """Return the newest readable, architecture-compatible CDM library.

    Chromium-based applications keep a component-updated CDM under
    ``~/.config/<app>/WidevineCdm`` (sometimes versioned). Those builds can
    be much newer than the distro package; prefer the newest one because
    Amazon's license service rejects older ARM64 CDMs with
    VMP_VALIDATION_FAILED.
    """
    host_arch = _host_elf_arch()
    best: Path | None = None
    best_key: tuple[Any, ...] | None = None
    for candidate in _candidate_paths():
        try:
            if not candidate.is_file() or not os.access(candidate, os.R_OK):
                continue
            if candidate.stat().st_size <= 0:
                continue
        except OSError:
            continue
        arch = _elf_arch(candidate)
        if host_arch and arch in ("aarch64", "x86_64") and arch != host_arch:
            continue
        version = _manifest_for(candidate).get("version", "")
        key = (
            _version_key(version if isinstance(version, str) else ""),
            1 if arch == host_arch else 0,
            1 if candidate != CDM_PATH else 0,
        )
        if best_key is None or key > best_key:
            best = candidate
            best_key = key
    return best


def build_widevine_flags(cdm: Path | None, existing: str = "") -> str:
    """Append the Widevine CDM flag if a CDM exists and no flag is set yet."""
    if WIDEVINE_CDM_FLAG in existing:
        return existing.strip()
    if cdm is None:
        return existing.strip()
    flag = f"{WIDEVINE_CDM_FLAG}={cdm}"
    return f"{existing} {flag}".strip() if existing.strip() else flag


def configure_widevine() -> Path | None:
    """Point QtWebEngine at the newest Widevine CDM before it initializes.

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
        log.info("using Widevine CDM %s at %s", cdm_version(cdm), cdm)
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


def _write_user_manifest(target: Path, cdm: Path) -> None:
    """Copy the selected CDM's manifest and add Linux platform entries."""
    manifest = dict(_manifest_for(cdm))
    platforms = manifest.setdefault("platforms", [])
    for platform_dir in _platform_dirs():
        arch = "arm64" if "arm64" in platform_dir else "x64"
        if not any(
            isinstance(entry, dict)
            and entry.get("os") == "linux"
            and entry.get("arch") == arch
            for entry in platforms
        ):
            platforms.append(
                {
                    "os": "linux",
                    "arch": arch,
                    "sub_package_path": f"_platform_specific/{platform_dir}/",
                }
            )
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))


def ensure_widevine_user_dir() -> None:
    """Point user-level WidevineCdm dirs at the newest usable CDM.

    QtWebEngine and Chromium discover Widevine through these directories.
    Existing symlinks that still point at the old distro CDM are updated so
    both discovery paths use the same (newer) build.
    """
    cdm = find_usable_cdm()
    if cdm is None:
        return
    try:
        selected = cdm.resolve()
    except OSError:
        selected = cdm
    try:
        old_system = CDM_PATH.resolve()
    except OSError:
        old_system = CDM_PATH
    home = Path.home()
    for base in (home / ".config" / "chromium", home / ".config" / "google-chrome"):
        target = base / "WidevineCdm"
        try:
            target.mkdir(parents=True, exist_ok=True)
            changed = False
            for platform_dir in _platform_dirs():
                sub = target / "_platform_specific" / platform_dir
                sub.mkdir(parents=True, exist_ok=True)
                link = sub / "libwidevinecdm.so"
                if link.is_symlink():
                    try:
                        current = link.resolve()
                    except OSError:
                        current = None
                    # Replace only a broken link or one pointing at the old
                    # distro CDM; never clobber a custom CDM.
                    if current != selected and (
                        current is None or current == old_system or not link.exists()
                    ):
                        link.unlink()
                        link.symlink_to(cdm)
                        changed = True
                elif not link.exists():
                    link.symlink_to(cdm)
                    changed = True
            if changed or not (target / "manifest.json").exists():
                _write_user_manifest(target, cdm)
                log.info("updated user-level WidevineCdm dir %s -> %s", target, cdm)
        except OSError as exc:
            log.debug("could not prepare widevine dir %s: %s", target, exc)


def run_stage_a() -> StageResult:
    return check_library_presence(find_usable_cdm() or CDM_PATH)


def format_stage(result: StageResult) -> str:
    lines = [f"[{result.stage}] {'OK' if result.ok else 'FAIL'}"]
    if result.error:
        lines.append(f"  error: {result.error}")
    for k, v in result.details.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)
