# Troubleshooting

- Missing WebEngine bindings: install qt6-qtwebengine and python3-pyside6.
- Missing CDM: install widevine-installer; check /var/lib/widevine.
- Playback errors after ~1s: the app passes `--widevine-cdm-path` automatically (check Diagnostics for the CDM in use). Codecs are not the cause (AAC/MP3 decode verified). Run **Diagnostics → Test CDM session**: if session creation fails, the CDM (4.10.2662.3, 2022) is rejected by Chromium 140 or Amazon; if it succeeds, the failure is at license acquisition (account/subscription/robustness).
- Incompatible CDM: check ELF arch with file command.
- Login loops: clear site data via Settings menu.
- Audio failures: check PipeWire/PulseAudio.
- Renderer crashes: check logs in ~/.local/state/amazon-music-desktop/logs.
