# DRM Compatibility

- Qt WebEngine: 6.11.2
- Chromium: 140.0.0.0
- Architecture: aarch64 (ELF 64-bit)
- System CDM: `/var/lib/widevine/libwidevinecdm.so` (4.10.2662.3, 2022)
- User-level CDM: component-updated builds under
  `~/.config/<app>/WidevineCdm/<version>/_platform_specific/linux_arm64/`
  (for example 4.10.3112.0).
- Bundled CDM: an RPM built with `--define 'bundled_cdm <path>'` installs the
  CDM under `/usr/lib64/amazon-music-desktop/WidevineCdm/` (or
  `/usr/lib/amazon-music-desktop/WidevineCdm/` on non-Fedora layouts). Such a
  build is for local use only and must not be redistributed.
- Discovery: the app scans the system install, the engine's hardcoded
  default path (read-only — on builds that ignore the flag, that file is
  the only one that can load, so selection must at least see it), the
  optional bundled directory, `~/.config/chromium`, `~/.config/google-chrome`,
  and versioned `WidevineCdm` directories from Chromium-based applications.
  A candidate is eligible only with a valid manifest (present, parseable,
  carrying a version, and — when it lists platforms — including the host
  arch) plus a host-arch ELF body, with one exception: a bare library
  sitting exactly at an engine default path is electable with unknown
  version when its ELF body is otherwise valid, since on affected builds
  it is the only file that can load (fully specified builds still sort
  above it). Malformed, manifest-less (elsewhere), and
  architecture-incompatible binaries are rejected — including an explicit
  `--widevine-cdm-path` pointing at one, which falls back to discovery with
  a warning instead of handing Chromium an unloadable file. It selects the
  newest eligible CDM.
- Initialization: the selected library is passed to QtWebEngine as
  `--widevine-cdm-path=<cdm>` via `QTWEBENGINE_CHROMIUM_FLAGS` before engine
  init (wired in `app.main()` ahead of `QApplication`, locked by
  `tests/unit/test_startup_wiring.py`). The app also creates or updates the
  user-level `WidevineCdm` directories so both discovery paths point at the
  same build.
  **Build caveat (verified 2026-10-31, `qt6-qtwebengine-6.11.2-2.fc44`): the
  engine ignores the switch** — it is absent from the engine binaries, a
  bogus flagged path is never attempted in verbose logs although the flag
  reaches the helper cmdline, and the loader always tries the hardcoded
  distro stub
  `/usr/lib64/chromium-browser/WidevineCdm/_platform_specific/linux_x64/libwidevinecdm.so`.
  That file is currently a 0-byte placeholder, so EME fails at
  `createMediaKeys()` (`CreateCdmFunc not available`) no matter which CDM
  the app selects. Repro without an Amazon account:
  `QT_QPA_PLATFORM=offscreen python3 scripts/probe-cdm-session.py`.
  Diagnostics shows this path under `Engine default CDM path`; the app never
  writes there. Until the engine loads a real CDM, the failure sits one
  stage *before* the license server and VMP cannot be re-tested.
- Loaded-CDM verification: Qt exposes no API for the CDM it actually loaded,
  so Diagnostics reports three independent facts side by side — the flag
  passed to the engine, the selected path/version, and `Observed mapped CDM`,
  a read-only scan of our own process tree's `/proc/*/maps` for mmapped
  `libwidevinecdm.so` binaries after first EME use. A mismatch between
  selected and observed paths means the engine loaded a different build.
- Diagnostics: three values are reported side by side and never conflated —
  **(1)** the CDM selected by Aurora (`CDM selected by Aurora`, a proposal),
  **(2)** the CDM at the engine's default location (`Engine default CDM
  path`), and **(3)** the CDM actually mapped into our helper processes
  (`Observed mapped CDM`), followed by a `Selection vs loaded verdict`
  (MATCH / MISMATCH / UNKNOWN). Only (3) is ground truth for what loaded.
  **Test CDM session** creates MediaKeys and a MediaKeySession to prove the
  CDM loads (and only that — it is not evidence of playback). Filesystem status is classified as NOT_INSTALLED,
  NOT_DISCOVERABLE, MANIFEST_INVALID, ARCH_INCOMPATIBLE, LIBRARY_MISSING, or
  READY (filesystem checks passed); INITIALIZED/INIT_FAILED come only from
  the live session probe, never from the filesystem.
- Audio codecs: AAC and MP3 decode verified working in stock QtWebEngine
  6.11.2 via `decodeAudioData` (2026-10-29).
- Amazon playback: the older 4.10.2662.3 build is rejected by Amazon's license
  service with `VMP_VALIDATION_FAILED`. The newer 4.10.3112.0 build is selected
  automatically when present; whether the license server accepts it is tested
  per `docs/LICENSE_VERIFICATION_RUNBOOK.md` on a host with an Amazon
  account, subscription, and audio output.
- Known limitation: only the native platform directory is ever written
  (`linux_arm64` on ARM64, `linux_x64` on x86_64). The host binary is never
  placed under the opposite architecture's path. Stale non-native links left
  by older app versions are removed when they point at managed CDM files;
  custom user CDMs are left untouched.

## Compatibility matrix

Only publish VERIFIED when actual protected playback has been tested on that
environment (spec section 9). Rows marked "not tested" are candidates, not
claims.

| Environment | Qt WebEngine | Widevine CDM | Playback |
|---|---|---|---|
| Fedora Asahi Remix 44 aarch64 | 6.11.2 (Chromium 140) | 4.10.3112.0 arm64 (component) preferred; 4.10.2662.3 arm64 rejected by license server (VMP_VALIDATION_FAILED) | engine ignores --widevine-cdm-path, tries 0-byte distro stub → createMediaKeys fails (2026-10-31); license stage unreachable; protected playback unverified |
| Fedora x86_64 | not tested | not tested | not tested |
| Fedora aarch64 (non-Asahi) | not tested | not tested | not tested |
| Debian x86_64 | not tested | not tested | not tested |
| Arch Linux x86_64 | not tested | not tested | not tested |
