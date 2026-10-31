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
- Discovery: the app scans the system install, the optional bundled directory,
  `~/.config/chromium`, `~/.config/google-chrome`, and versioned `WidevineCdm`
  directories from Chromium-based applications. It selects the newest readable
  CDM whose ELF architecture matches the host.
- Initialization: the selected library is passed to QtWebEngine as
  `--widevine-cdm-path=<cdm>` via `QTWEBENGINE_CHROMIUM_FLAGS` before engine
  init. The app also creates or updates the user-level `WidevineCdm`
  directories so both discovery paths point at the same build.
- Diagnostics: **Diagnostics → CDM in use / CDM version** reports the selected
  path and version. **Test CDM session** creates MediaKeys and a
  MediaKeySession to prove the CDM loads (and only that — it is not evidence
  of playback). CDM install status is classified as NOT_INSTALLED,
  NOT_DISCOVERABLE, MANIFEST_INVALID, ARCH_INCOMPATIBLE, or LIBRARY_MISSING;
  INITIALIZED/INIT_FAILED come only from the live session probe.
- Audio codecs: AAC and MP3 decode verified working in stock QtWebEngine
  6.11.2 via `decodeAudioData` (2026-10-29).
- Amazon playback: the older 4.10.2662.3 build is rejected by Amazon's license
  service with `VMP_VALIDATION_FAILED`. The newer 4.10.3112.0 build is selected
  automatically when present; protected playback must be verified on a host
  with an Amazon account, subscription, and audio output.
- Known limitation: Qt builds may hardcode the `linux_x64` Widevine path; the
  app therefore maintains both `linux_x64` and `linux_arm64` symlinks in its
  user-level CDM directories.

## Compatibility matrix

Only publish VERIFIED when actual protected playback has been tested on that
environment (spec section 9). Rows marked "not tested" are candidates, not
claims.

| Environment | Qt WebEngine | Widevine CDM | Playback |
|---|---|---|---|
| Fedora Asahi Remix 44 aarch64 | 6.11.2 (Chromium 140) | 4.10.3112.0 arm64 (component) preferred; 4.10.2662.3 arm64 rejected by license server (VMP_VALIDATION_FAILED) | CDM loads (MediaKeySession OK); protected playback unverified (needs account) |
| Fedora x86_64 | not tested | not tested | not tested |
| Fedora aarch64 (non-Asahi) | not tested | not tested | not tested |
| Debian x86_64 | not tested | not tested | not tested |
| Arch Linux x86_64 | not tested | not tested | not tested |
