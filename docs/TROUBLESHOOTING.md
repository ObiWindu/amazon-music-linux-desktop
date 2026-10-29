# Troubleshooting

- Missing WebEngine bindings: install qt6-qtwebengine and python3-pyside6.
- Missing CDM: install widevine-installer; check /var/lib/widevine.
- Playback errors after ~1s on Fedora: the app passes `--widevine-cdm-path` automatically (check Diagnostics for the CDM in use). If it still fails, missing proprietary codecs in stock `qt6-qtwebengine` is the likely cause; no freeworld Qt6 WebEngine build is published for Fedora 44 aarch64.
- Incompatible CDM: check ELF arch with file command.
- Login loops: clear site data via Settings menu.
- Audio failures: check PipeWire/PulseAudio.
- Renderer crashes: check logs in ~/.local/state/amazon-music-desktop/logs.
