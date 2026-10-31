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

# Native platform directory for *writing* user-level CDM links. Discovery may
# scan the fallback name too (validated by ELF architecture), but we must never
# write an ARM64 binary to a linux_x64 path or vice versa — that would be a
# fake architecture mapping (remediation spec 2.1).
_NATIVE_PLATFORM_DIR: dict[str, str] = {
    "aarch64": "linux_arm64",
    "arm64": "linux_arm64",
    "x86_64": "linux_x64",
    "amd64": "linux_x64",
}


def _native_platform_dir() -> str:
    """Return the single Widevine platform dir matching this host."""
    return _NATIVE_PLATFORM_DIR.get(platform.machine().lower(), "linux_arm64")

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


def _explicit_cdm() -> Path | None:
    """Return a CDM explicitly requested via QTWEBENGINE_CHROMIUM_FLAGS.

    The explicit path is held to the same bar as auto-discovered builds:
    it must exist, be readable, be non-empty, and its ELF architecture must
    match the host. A malformed or incompatible explicit CDM is rejected
    (with a warning) so Chromium is never handed a binary it cannot load;
    discovery then falls back to the newest usable build.
    """
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    host_arch = _host_elf_arch()
    for token in flags.split():
        if not token.startswith(f"{WIDEVINE_CDM_FLAG}="):
            continue
        candidate = Path(token.split("=", 1)[1])
        try:
            if not (candidate.is_file() and os.access(candidate, os.R_OK)):
                continue
            if candidate.stat().st_size <= 0:
                log.warning("ignoring explicit CDM %s: empty file", candidate)
                continue
        except OSError:
            continue
        arch = _elf_arch(candidate)
        if host_arch and arch in ("aarch64", "x86_64") and arch != host_arch:
            log.warning(
                "ignoring explicit CDM %s: architecture mismatch (CDM is %s, host is %s)",
                candidate,
                arch,
                host_arch,
            )
            continue
        if arch in ("not-elf",) or arch.startswith(("error:", "unknown(")):
            log.warning("ignoring explicit CDM %s: not a loadable library (%s)", candidate, arch)
            continue
        return candidate
    return None


def find_usable_cdm() -> Path | None:
    """Return the newest readable, architecture-compatible CDM library.

    An explicit ``--widevine-cdm-path`` in QTWEBENGINE_CHROMIUM_FLAGS wins.
    Otherwise, Chromium-based applications keep a component-updated CDM under
    ``~/.config/<app>/WidevineCdm`` (sometimes versioned). Those builds can
    be much newer than the distro package; prefer the newest one because
    Amazon's license service rejects older ARM64 CDMs with
    VMP_VALIDATION_FAILED.
    """
    explicit = _explicit_cdm()
    if explicit is not None:
        return explicit
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
        # Reject malformed and incompatible binaries: when the host arch is
        # known only an exact host-arch ELF is eligible; otherwise any
        # non-ELF, unreadable, or unknown-machine file is skipped. A text
        # file or wrong-arch library named libwidevinecdm.so is never
        # selected or handed to Chromium.
        if host_arch:
            if arch != host_arch:
                continue
        elif arch in ("not-elf",) or arch.startswith(("error:", "unknown(")):
            continue
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

    Caveat (verified 2026-10-31): Fedora's qt6-qtwebengine-6.11.2 ignores
    --widevine-cdm-path — the string is absent from its binaries, a bogus
    flagged path is never attempted in verbose logs, and the engine always
    tries its hardcoded distro stub instead. The flag is still set because
    other Qt/Chromium builds honor it; on affected builds use
    engine_cdm_status() and the headless probe to see what actually loads.
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
        if st.st_size <= 0:
            return StageResult("A_library_presence", False, details, "CDM file is empty")
    except OSError as exc:
        return StageResult("A_library_presence", False, details, str(exc))
    # ELF arch: validated against the *host* runtime architecture, never a
    # hard-coded one (remediation spec 2.1).
    arch = _elf_arch(cdm_path)
    details["arch"] = arch
    host = _host_elf_arch()
    if host is not None:
        details["host_arch"] = host
    if arch == "not-elf":
        return StageResult("A_library_presence", False, details, "CDM file is not an ELF library")
    if host is not None and arch in ("aarch64", "x86_64") and arch != host:
        return StageResult(
            "A_library_presence",
            False,
            details,
            f"architecture mismatch: CDM is {arch}, host is {host}",
        )
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
    """Copy the selected CDM's manifest and add the native Linux entry."""
    manifest = dict(_manifest_for(cdm))
    platforms = manifest.setdefault("platforms", [])
    native = _native_platform_dir()
    arch = "arm64" if "arm64" in native else "x64"
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
                "sub_package_path": f"_platform_specific/{native}/",
            }
        )
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _is_managed_cdm(path: Path) -> bool:
    """Return True for a CDM under a system or bundled managed root."""
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in (CDM_PATH, WIDEVINE_CDM_DIR, *BUNDLED_CDM_DIRS):
        try:
            root_resolved = root.resolve()
        except OSError:
            root_resolved = root
        if resolved.is_relative_to(root_resolved):
            return True
    return False


def ensure_widevine_user_dir() -> None:
    """Point user-level WidevineCdm dirs at the newest usable CDM.

    QtWebEngine and Chromium discover Widevine through these directories.
    (Caveat: Fedora's qt6-qtwebengine-6.11.2 ignores both these directories
    and --widevine-cdm-path — verified 2026-10-31 — so on that build they
    serve Chromium/Electron component discovery only. They are still
    maintained because other builds honor them.)
    Only the native platform directory (``linux_arm64`` on ARM64,
    ``linux_x64`` on x86_64) is maintained — writing the host binary under
    the opposite architecture's path would be a fake mapping and is never
    done. Stale non-native links created by older app versions that point at
    a managed system/bundled CDM are removed; custom user CDMs are left
    untouched. Symlinks that point at a system or bundled CDM are updated so
    both discovery paths use the same (newer) build. A custom user CDM is left
    untouched.
    """
    cdm = find_usable_cdm()
    if cdm is None:
        return
    try:
        selected = cdm.resolve()
    except OSError:
        selected = cdm
    native = _native_platform_dir()
    fallbacks = [d for d in _platform_dirs() if d != native]
    home = Path.home()
    for base in (home / ".config" / "chromium", home / ".config" / "google-chrome"):
        target = base / "WidevineCdm"
        try:
            target.mkdir(parents=True, exist_ok=True)
            # Clean up stale non-native links from older app versions that
            # placed the host binary under the fallback arch path. Only
            # remove symlinks pointing at managed files (or broken links);
            # a custom user CDM under the fallback path is left alone.
            for platform_dir in fallbacks:
                stale = target / "_platform_specific" / platform_dir / "libwidevinecdm.so"
                try:
                    if stale.is_symlink():
                        try:
                            current = stale.resolve()
                        except OSError:
                            current = None
                        if current is None or _is_managed_cdm(current):
                            stale.unlink()
                            log.info("removed stale non-native CDM link %s", stale)
                except OSError as exc:
                    log.debug("could not clean stale cdm link %s: %s", stale, exc)
            changed = False
            sub = target / "_platform_specific" / native
            sub.mkdir(parents=True, exist_ok=True)
            link = sub / "libwidevinecdm.so"
            if link.is_symlink():
                try:
                    current = link.resolve()
                except OSError:
                    current = None
                # Replace a broken link or one pointing at a managed
                # system/bundled CDM; never clobber a custom CDM.
                if current != selected and (
                    current is None or _is_managed_cdm(current) or not link.exists()
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


CDM_ARCH_FOR_HOST: dict[str, str] = {"x86_64": "x64", "aarch64": "arm64"}


def host_cdm_arch() -> str | None:
    """Return the expected Widevine manifest arch for this host, if known."""
    return CDM_ARCH_FOR_HOST.get(_host_elf_arch() or "")


def validate_cdm_manifest(cdm: Path) -> StageResult:
    """Validate the Widevine manifest next to *cdm* (remediation spec 2.2)."""
    details: dict[str, Any] = {"path": str(cdm)}
    manifest = _manifest_for(cdm)
    if not manifest:
        return StageResult("D_manifest", False, details, "manifest.json missing or unreadable")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        return StageResult("D_manifest", False, details, "manifest.json has no version")
    details["version"] = version
    archs = sorted(
        {
            arch
            for entry in manifest.get("platforms", [])
            if isinstance(entry, dict)
            for arch in [entry.get("arch")]
            if isinstance(arch, str)
        }
    )
    details["manifest_archs"] = archs
    expected = host_cdm_arch()
    if expected and archs and expected not in archs:
        return StageResult(
            "D_manifest",
            False,
            details,
            f"manifest platforms {archs} do not include {expected}",
        )
    return StageResult("D_manifest", True, details)


def cdm_install_status(cdm: Path | None) -> str:
    """Classify a discovered CDM installation at the filesystem level.

    One of NOT_INSTALLED, NOT_DISCOVERABLE, MANIFEST_INVALID,
    ARCH_INCOMPATIBLE, LIBRARY_MISSING, or READY (filesystem validation
    passed). Initialization results (INIT_FAILED / INITIALIZED) are only
    observable through the live CDM session probe in the diagnostics dialog
    and are never inferred here.
    """
    if cdm is None:
        return "NOT_INSTALLED"
    if not cdm.exists():
        return "NOT_INSTALLED"
    if not cdm.is_file():
        return "NOT_DISCOVERABLE"
    try:
        if not os.access(cdm, os.R_OK):
            return "LIBRARY_MISSING"
        arch = _elf_arch(cdm)
    except OSError:
        return "LIBRARY_MISSING"
    if arch == "not-elf":
        return "LIBRARY_MISSING"
    host = _host_elf_arch()
    if host is not None and arch in ("aarch64", "x86_64") and arch != host:
        return "ARCH_INCOMPATIBLE"
    manifest = _manifest_for(cdm)
    if not manifest:
        return "MANIFEST_INVALID"
    return "READY"


def cdm_inventory() -> list[dict[str, Any]]:
    """All discoverable CDM binaries with validation details.

    Each entry records the manifest version (when present), the actual ELF
    architecture, whether it matches the host, and whether discovery selected
    it. Newest is not claimed to be most compatible — selection prefers the
    newest because the license server rejected the old 2022 ARM64 build.
    """
    host = _host_elf_arch()
    selected = find_usable_cdm()
    entries: list[dict[str, Any]] = []
    for path in _candidate_paths():
        try:
            if not path.is_file() or not os.access(path, os.R_OK):
                continue
            size = path.stat().st_size
            # Skip zero-size placeholder files shipped by some distro
            # packages (e.g. an empty linux_x64 stub on ARM64 systems);
            # they are not loadable CDMs.
            if size <= 0:
                continue
        except OSError:
            continue
        manifest = _manifest_for(path)
        version = manifest.get("version")
        entries.append(
            {
                "path": str(path),
                "version": version if isinstance(version, str) else None,
                "arch": _elf_arch(path),
                "manifest_valid": bool(manifest),
                "arch_match": (_elf_arch(path) == host) if host else None,
                "size": size,
                "selected": path == selected,
            }
        )
    return entries


def _descendant_pids(proc_root: Path, root_pid: int) -> set[int]:
    """Return root_pid plus all transitive children via /proc ppid links."""
    children: dict[int, list[int]] = {}
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return {root_pid}
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        try:
            ppid = int(stat[stat.rfind(")") + 1 :].split()[1])
        except (IndexError, ValueError):
            continue
        children.setdefault(ppid, []).append(pid)
    seen = {root_pid}
    queue = [root_pid]
    while queue:
        for child in children.get(queue.pop(), []):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return seen


def loaded_cdm_paths(
    proc_root: Path | str = "/proc", scope: str = "all"
) -> list[dict[str, Any]]:
    """Observe which libwidevinecdm.so binaries live processes have mapped.

    Qt WebEngine exposes no public API for the CDM it actually loaded — the
    ``--widevine-cdm-path`` flag only states intent, and the EME session
    probe only proves *a* CDM instantiated. After first EME use, however,
    Chromium mmaps the loaded CDM into its helper (QtWebEngineProcess)
    address space, and that mapping is locally observable through
    ``/proc/<pid>/maps``. Each entry reports the pid and mapped path.

    ``scope="tree"`` limits the scan to this process and its descendants
    (i.e. our own QtWebEngine helpers — the attribution that matters);
    ``scope="all"`` scans every visible process. An empty result means no
    mapping is currently visible (EME not yet used, helper not yet spawned,
    or maps unreadable) — never evidence of failure.

    This is read-only local introspection: no CDM, license, or page data is
    touched.
    """
    if scope not in ("all", "tree"):
        raise ValueError(f"unknown scope: {scope!r}")
    root = Path(proc_root)
    allowed: set[int] | None = None
    if scope == "tree":
        allowed = _descendant_pids(root, os.getpid())
    found: dict[tuple[int, str], None] = {}
    try:
        entries = list(root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if allowed is not None and pid not in allowed:
            continue
        try:
            maps = (entry / "maps").read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        for line in maps.splitlines():
            if "libwidevinecdm.so" not in line:
                continue
            # maps format: address perms offset dev inode pathname
            parts = line.split(None, 5)
            if len(parts) < 6:
                continue
            path = parts[5].strip()
            if path.endswith(" (deleted)"):
                path = path[: -len(" (deleted)")].strip()
            if not path.startswith("/"):
                continue
            found.setdefault((pid, path))
            if len(found) >= 50:
                break
        if len(found) >= 50:
            break
    return [{"pid": pid, "path": path} for pid, path in sorted(found)]


def observed_loaded_cdm(
    proc_root: Path | str = "/proc", scope: str = "all"
) -> list[str]:
    """Sorted unique CDM paths currently mapped by live processes."""
    seen: list[str] = []
    for entry in loaded_cdm_paths(proc_root, scope=scope):
        path = entry["path"]
        if path not in seen:
            seen.append(path)
    return seen


# Engine-default CDM locations observed at runtime, per build/distro.
# Verified 2026-10-31: Fedora's qt6-qtwebengine-6.11.2 ignores the
# --widevine-cdm-path switch entirely (the string is absent from its
# binaries and a bogus flagged path is never attempted in verbose logs)
# and instead always tries this distro stub path. Labeled as observed
# behavior of a specific build, not a portable assumption.
ENGINE_DEFAULT_CDM_PATHS: tuple[Path, ...] = (
    Path("/usr/lib64/chromium-browser/WidevineCdm/_platform_specific/linux_x64/libwidevinecdm.so"),
)


def engine_cdm_status() -> list[dict[str, Any]]:
    """Report the CDM binaries at the engine's hardcoded default paths.

    This is the ground truth for *which file* the engine will attempt when
    the build ignores --widevine-cdm-path: a 0-byte or missing file here
    means EME fails at createMediaKeys no matter which CDM the app selected.
    Entries are observational only; the app never writes to these paths.
    """
    entries: list[dict[str, Any]] = []
    for path in ENGINE_DEFAULT_CDM_PATHS:
        entry: dict[str, Any] = {"path": str(path)}
        try:
            exists = path.is_file()
        except OSError:
            exists = False
        entry["present"] = exists
        if not exists:
            entry["state"] = "missing"
            entries.append(entry)
            continue
        try:
            size = path.stat().st_size
        except OSError:
            entry["state"] = "unreadable"
            entries.append(entry)
            continue
        entry["size"] = size
        entry["arch"] = _elf_arch(path)
        if size <= 0:
            entry["state"] = "placeholder: 0-byte file, CDM cannot load"
        elif entry["arch"] == "not-elf":
            entry["state"] = "unloadable: not an ELF library"
        else:
            entry["state"] = "candidate: engine will attempt this file"
        entries.append(entry)
    return entries


def cdm_version_comparison() -> dict[str, Any]:
    """Compare system vs selected vs flag-passed CDM (remediation spec 4.4).

    The CDM Qt WebEngine actually loaded is not observable through public
    APIs; the live CDM session probe in the diagnostics dialog is the check
    for that, and its result is recorded in the playback pipeline.
    """
    selected = find_usable_cdm()
    system_present = CDM_PATH.is_file()
    return {
        "system_cdm": {
            "path": str(CDM_PATH),
            "present": system_present,
            "version": cdm_version(CDM_PATH) if system_present else None,
        },
        "selected_cdm": {
            "path": str(selected) if selected else None,
            "version": cdm_version(selected) if selected else None,
        },
        "flag_passed": build_widevine_flags(selected, "") if selected else None,
        "candidates": cdm_inventory(),
        "qt_webengine_loaded": (
            "not directly observable through Qt APIs; use the live CDM session "
            "probe plus the 'Observed mapped CDM' process-tree scan in diagnostics"
        ),
    }


def run_stage_a() -> StageResult:
    return check_library_presence(find_usable_cdm() or CDM_PATH)


def format_stage(result: StageResult) -> str:
    lines = [f"[{result.stage}] {'OK' if result.ok else 'FAIL'}"]
    if result.error:
        lines.append(f"  error: {result.error}")
    for k, v in result.details.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)
