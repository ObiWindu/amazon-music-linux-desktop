# Troubleshooting

- Missing WebEngine bindings: install qt6-qtwebengine and python3-pyside6.
- Missing CDM: install widevine-installer; check /var/lib/widevine.
- Playback starts, then stops after ~1s: observed sequence (Chromium verbose log): audio plays ~0.5-1s → Amazon requests the DRM license (`music.amazon.fr/ZAZ/api/dmls/`) → `DrmControllerImpl` errors → the page closes the stream, retries once, gives up. Cause: Amazon's license service rejecting the request for the 2022-era linux-arm64 CDM (4.10.2662.3, the last ARM64 Linux build published). Codecs are not the cause (AAC/MP3 decode verified), and neither is the app's player UI. No client-side fix is known.
- Playback errors after ~1s: the app passes `--widevine-cdm-path` automatically (check Diagnostics for the CDM in use). Run **Diagnostics → Test CDM session**: if session creation fails, the CDM is rejected by Chromium 140; if it succeeds (as observed), the failure is at license acquisition.
- The Amazon web player bar is never visible by design: the web view is docked so the page's bottom-docked player bar renders outside the visible window (`main_window._BrowserHost`). The page player is otherwise untouched — modifying its DOM/CSS correlated with playback teardowns. The native bottom bar drives it via clicks and mirrors its state via polling.
- Incompatible CDM: check ELF arch with file command.
- Login loops: clear site data via Settings menu.
- Audio failures: check PipeWire/PulseAudio.
- `ffmpeg not found` or unsupported-codec errors from `scripts/convert-to-mp3.sh`: on Fedora install the freeworld codec library from RPM Fusion free — `sudo dnf install ffmpeg libavcodec-freeworld` (stock Fedora uses `libavcodec-free`, which lacks some codecs).
- Renderer crashes: check logs in ~/.local/state/amazon-music-desktop/logs.
