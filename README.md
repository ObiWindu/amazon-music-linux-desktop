# Amazon Music Desktop (Aurora Music Desktop)

A native desktop application for Amazon Music on Linux, built with Python 3, PySide6, and Qt WebEngine (Chromium 140). Designed for Fedora Asahi Remix on Apple Silicon (AArch64), and packaged for Fedora, Debian/Ubuntu, and Arch Linux.

## Features

- Dedicated desktop window for Amazon Music using Amazon's own website and authentication.
- Persistent browser profile (login survives restarts) stored under `~/.local/share/amazon-music-desktop`.
- Regional homepage selection (France, US, UK, Germany) with persisted preference.
- Amazon Music-like shell: left sidebar (Home, Search, Library, Playlists, Favorites), embedded settings page, bottom player/status bar.
- Widevine DRM diagnostics and automatic user-level CDM directory setup.
- Origin security policy with hostname boundary checks; dangerous schemes blocked.
- Download confirmation and destination validation.
- Restrictive file permissions (0700) for profile and config data.
- Redacted logging; no credentials, cookies, or tokens stored in config.
- Optional system tray integration.
- Automated tests (unit, security, integration), lint (ruff), type checks (mypy).
- Packaging for RPM, Debian, and Arch; GitHub Actions CI.

## Requirements

- Linux (AArch64 recommended; x86_64 may work with a compatible Widevine CDM).
- Python 3.11+
- PySide6 (with Qt WebEngine bindings)
- Qt 6 WebEngine (Chromium-based)
- A working audio subsystem (PipeWire/PulseAudio)
- A graphical desktop session (Wayland or X11)

### Widevine CDM

Widevine is required for protected playback. The application does not bundle the proprietary CDM (licensing). Install it per distribution:

- **Fedora / Fedora Asahi Remix**: `sudo dnf install widevine-installer` (provides `/var/lib/widevine/libwidevinecdm.so`). On Apple Silicon, the installer handles the 16K-page-size fixup.
- **Fedora codecs note**: AAC/MP3 decode verified working in stock `qt6-qtwebengine` 6.11.2. No `qt6-qtwebengine-freeworld` build is published for Fedora 44 aarch64 (and it isn't needed for audio). If protected playback fails after ~1 second, the cause is on the Widevine side — use **Diagnostics → Test CDM session** to check whether the CDM loads.
- **Debian / Ubuntu**: install `chromium-widevine` (or Google Chrome) which provides a `WidevineCdm` directory under `~/.config/chromium` or `/usr/lib/chromium`.
- **Arch Linux**: install `chromium-widevine` from the AUR, or `google-chrome`.

On first launch, the app creates `~/.config/chromium/WidevineCdm` pointing at the system CDM if it is present. Run **Diagnostics** from the sidebar to verify detection.

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
5. Use **Diagnostics** to inspect system, browser, and Widevine status.
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
- Actual protected playback requires a valid Amazon account and subscription; not verified in this environment.
- See `docs/DRM_COMPATIBILITY.md` and `evidence/DRM_REPORT.md`.

## Troubleshooting

See `docs/TROUBLESHOOTING.md`. Common issues:

- **Missing WebEngine bindings**: install `qt6-qtwebengine` and `python3-pyside6`.
- **Widevine not detected**: install the distro CDM package; run Diagnostics.
- **Incompatible CDM**: check ELF architecture with `file /var/lib/widevine/libwidevinecdm.so`.
- **Login loops**: clear site data via Settings → (or File menu).
- **Audio failures**: check PipeWire/PulseAudio.
- **Renderer crashes**: review logs in `~/.local/state/amazon-music-desktop/logs/`.

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/SECURITY.md`
- `docs/DRM_COMPATIBILITY.md`
- `docs/TESTING.md`
- `docs/INSTALLATION.md`
- `docs/TROUBLESHOOTING.md`

## License

MIT (see `LICENSE`).
