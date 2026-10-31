# Amazon Music Desktop (Aurora Music Desktop)

A native desktop application for Amazon Music on Linux, built with Python 3, PySide6, and Qt WebEngine (Chromium 140). Designed for Fedora Asahi Remix on Apple Silicon (AArch64), and packaged for Fedora, Debian/Ubuntu, and Arch Linux.

## Features

- Dedicated desktop window for Amazon Music using Amazon's own website and authentication.
- Persistent browser profile (login survives restarts) stored under `~/.local/share/amazon-music-desktop`.
- Regional homepage selection (France, US, UK, Germany) with persisted preference.
- Amazon Music-like shell: left sidebar (Home, Search, Library, Playlists, Favorites), embedded settings page, bottom player/status bar.
- Widevine DRM diagnostics and automatic user-level CDM directory setup.
- Playback monitor: normalized playback state from browser media events (not just DOM polling), with stall/error detection and a playback pipeline diagnostic model.
- Settings → Playback diagnostics: run diagnostics, copy a redacted report, open troubleshooting documentation.
- MPRIS D-Bus integration: desktop media controls and metadata sync (the browser page remains the playback authority).
- Origin security policy with hostname boundary checks; dangerous schemes blocked.
- Download confirmation and destination validation.
- Restrictive file permissions (0700) for profile and config data.
- Redacted logging; no credentials, cookies, or tokens stored in config.
- Optional system tray integration.
- Automated tests (unit, security, integration), lint (ruff), type checks (mypy).
- Packaging for RPM, Debian, and Arch; GitHub Actions CI.

## Playback & DRM status (honest)

| Level | Status |
|---|---|
| CDM detected | Yes — system (4.10.2662.3) and component-updated (4.10.3112.0) ARM64 builds; architecture-validated |
| CDM initialized | Yes — MediaKeys + MediaKeySession creation verified live with 4.10.3112.0 |
| License accepted | No — 4.10.2662.3 is rejected by Amazon (`VMP_VALIDATION_FAILED`, HTTP 400); 4.10.3112.0 not yet verified against the license server |
| Playback verified | No — protected playback has not been successfully tested on any configuration yet |

Details and the full failure timeline: `evidence/PLAYBACK_FAILURE_TIMELINE.md`.
If Amazon rejects the newer build too, that is a device-eligibility
limitation of this environment and will be documented here rather than
worked around.

## Requirements

- Linux (AArch64 recommended; x86_64 may work with a compatible Widevine CDM).
- Python 3.11+
- PySide6 (with Qt WebEngine bindings)
- Qt 6 WebEngine (Chromium-based)
- A working audio subsystem (PipeWire/PulseAudio)
- A graphical desktop session (Wayland or X11)

### Widevine CDM

Widevine is required for protected playback. The default RPM does not bundle the proprietary CDM (licensing). Install it per distribution:

- **Fedora / Fedora Asahi Remix**: `sudo dnf install widevine-installer` (provides `/var/lib/widevine/libwidevinecdm.so`). On Apple Silicon, the installer handles the 16K-page-size fixup.
- **Fedora codecs note**: AAC/MP3 decode verified working in stock `qt6-qtwebengine` 6.11.2. On Fedora the freeworld codec library is `libavcodec-freeworld` (RPM Fusion free); no `qt6-qtwebengine-freeworld` build is published for Fedora 44 aarch64, and it isn't needed for in-app audio. If protected playback fails after ~1 second, the cause is on the Widevine side — use **Diagnostics → Test CDM session** and check the CDM version it reports. The app prefers the newest CDM it can find, including component-updated builds under `~/.config/<app>/WidevineCdm/<version>/`.
- **Debian / Ubuntu**: install `chromium-widevine` (or Google Chrome) which provides a `WidevineCdm` directory under `~/.config/chromium` or `/usr/lib/chromium`.
- **Arch Linux**: install `chromium-widevine` from the AUR, or `google-chrome`.

For a private, local-only RPM that embeds an already-installed CDM, see `packaging/widevine/README.md`. Do not redistribute that build: Google's Widevine license prohibits it.

On first launch, the app creates or updates `~/.config/chromium/WidevineCdm` and `~/.config/google-chrome/WidevineCdm` to point at the newest CDM it finds (the distro package or a newer component-updated build). Run **Diagnostics** from the sidebar to verify detection and the CDM version in use.

## Installation

### Fedora (RPM)

```bash
sudo dnf install ./amazon-music-desktop-0.1.0-1.fc44.noarch.rpm
```

Then launch from the application menu or run `amazon-music-desktop`.

### Debian / Ubuntu

```bash
cd packaging/debian
dpkg-buildpackage -us -uc -b
sudo apt install ../amazon-music-desktop_0.1.0-1_all.deb
```

### Arch Linux

```bash
cd packaging/arch
makepkg -si
```

### From source

```bash
PYTHONPATH=src python3 -m amazon_music_desktop
```

Or use the helper:

```bash
./scripts/run-dev.sh
```

## Usage

1. Launch the application.
2. Sign in through Amazon's own login flow (no credentials are collected by the app).
3. Use the sidebar to navigate Home, Search, Library, Playlists, and Favorites.
4. Open **Settings** (sidebar) to change region, homepage, window size, tray, etc.
5. Use **Diagnostics** to inspect system, browser, Widevine, and playback-pipeline status (also under **Settings → Playback diagnostics**, with report copy and troubleshooting links).
6. **Clear site data** from the File menu to sign out.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+R | Reload |
| Alt+Left | Back |
| Alt+Right | Forward |
| Ctrl+H | Home |
| Ctrl+, | Settings |
| Ctrl+Q | Quit |

## Data locations

| Purpose | Path |
|---|---|
| Config | `~/.config/amazon-music-desktop/` |
| Profile (cookies/session) | `~/.local/share/amazon-music-desktop/profile/` |
| Cache | `~/.local/share/amazon-music-desktop/cache/` |
| Logs | `~/.local/state/amazon-music-desktop/logs/` |

Profile directories use `0700` permissions. Package removal does not delete user data.

## Convert audio to MP3

`scripts/convert-to-mp3.sh` converts local audio files (any ffmpeg-supported codec) to MP3:

```bash
./scripts/convert-to-mp3.sh song.flac song.ogg
./scripts/convert-to-mp3.sh -b 256k -o ~/Music/mp3 *.m4a
```

It never overwrites (suffixed copies) and skips files already in MP3 unless `-f` is given. For local, user-owned files only — it cannot process DRM-protected streams.

On Fedora, install the full codec library from RPM Fusion free so the `ffmpeg` CLI can decode all formats: `sudo dnf install ffmpeg libavcodec-freeworld` (requires the RPM Fusion free repo). Stock Fedora ships `ffmpeg-free`/`libavcodec-free`, which lacks some codecs.

## Testing

```bash
./scripts/run-tests.sh
```

Or:

```bash
python3 -m pytest                # all tests
python3 -m pytest tests/unit tests/security   # unit + security
python3 -m pytest tests/integration            # GUI (needs display)
```

Lint and type checks:

```bash
python3 -m ruff check src tests
python3 -m mypy src --ignore-missing-imports
```

Release verification:

```bash
./scripts/verify-release.sh
```

## Packaging

- RPM spec: `packaging/rpm/amazon-music-desktop.spec`
- Debian: `packaging/debian/`
- Arch: `packaging/arch/PKGBUILD`

Build the RPM (on Fedora):

```bash
rpmbuild -ba packaging/rpm/amazon-music-desktop.spec
```

## Security

See `docs/SECURITY.md`. Highlights:

- No separate password system; authentication handled by Amazon.
- Navigation policy blocks `javascript:`, `data:`, `file:`, `ftp:`, `intent:` and validates hostnames with boundary checks.
- External links open in the system browser.
- Downloads require confirmation and validated destinations.
- Logs and support bundles redact sensitive data.
- No QWebChannel bridge; no privileged Python objects exposed to web content.

## Widevine / DRM limitations

- Detection of EME or `com.widevine.alpha` does not guarantee playback.
- Protected playback with the 2022 ARM64 CDM (4.10.2662.3, from the widevine-installer LaCrOS 120 image) is blocked server-side on Fedora Asahi. An instrumented live run shows: EME session created, `generateRequest` succeeds, then Amazon's license service (`music.amazon.fr/ZAZ/api/dmls/`) responds HTTP 400 with `com.amazon.digitalmusicdrmlicenseservice#ForbiddenException`, `denialReason: VMP_VALIDATION_FAILED` — "UNVERIFIED request not eligible for LD content". Amazon validates the Widevine Verified Media Path attestation, and that older build fails it.
- The app now discovers and prefers the newest readable CDM across the system package and user-level Chromium component directories (`~/.config/<app>/WidevineCdm/<version>/_platform_specific/linux_arm64/`). On this host, 4.10.3112.0 is selected instead of 4.10.2662.3; Diagnostics reports the version in use. If playback still fails with `VMP_VALIDATION_FAILED`, confirm Diagnostics shows 4.10.3112.0 or newer.
- The Amazon web player bar is never shown: the web view is docked so its bottom strip (where the page's player bar renders) is outside the visible window. The page player itself is left completely untouched — no CSS, DOM, or layout modification — because touching it correlated with playback teardowns. The native bottom bar is the only visible player surface.
- The native player bar (`src/amazon_music_desktop/ui/player_bar.py`) is fully functional and locale-independent: play/pause toggles the page media element directly; next/previous/shuffle/repeat click the page's transport buttons via known data-testid/aria-label patterns (fr, en) with a geometry fallback that addresses the [shuffle prev play next repeat] cluster inside Amazon's docked bar strip by x position. Every button animates on press (scale "pop"), shows a hover fill and a pulsing ring while playing; the bar also mirrors title, elapsed/total time and volume, and supports click-to-seek, volume/mute and media-key shortcuts (Media Play/Pause/Next/Previous).
- The song queue lives in a panel on the **right** (`src/amazon_music_desktop/ui/queue_panel.py`) and shows songs only. Song identity comes from `navigator.mediaSession.metadata` (falling back to the page title) — playlist names and other page titles are never listed; a song counts as soon as the page player has *loaded* it (duration known, playing or paused), so the panel is never empty during a session. A read-only best-effort scrape of the page's own up-next rows replaces the feed when the page exposes its real queue, and a "No songs yet — press play" note is shown while the list is empty.
- Actual protected playback requires a valid Amazon account and subscription.
- See `docs/DRM_COMPATIBILITY.md` and `evidence/DRM_REPORT.md`.

## Troubleshooting

See `docs/TROUBLESHOOTING.md`. Common issues:

- **Missing WebEngine bindings**: install `qt6-qtwebengine` and `python3-pyside6`.
- **Widevine not detected**: install the distro CDM package; run Diagnostics.
- **Incompatible CDM**: check Diagnostics → CDM in use, then verify its ELF architecture with `file <path>`.
- **Login loops**: clear site data via Settings → (or File menu).
- **Audio failures**: check PipeWire/PulseAudio.
- **Renderer crashes**: review logs in `~/.local/state/amazon-music-desktop/logs/`.

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/SECURITY.md`
- `docs/DRM_COMPATIBILITY.md`
- `docs/LICENSE_VERIFICATION_RUNBOOK.md`
- `docs/TESTING.md`
- `docs/INSTALLATION.md`
- `docs/TROUBLESHOOTING.md`

## License

MIT (see `LICENSE`).
