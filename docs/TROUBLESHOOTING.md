# Troubleshooting

- Missing WebEngine bindings: install qt6-qtwebengine and python3-pyside6.
- Missing CDM: install widevine-installer; check /var/lib/widevine.
- Playback errors after ~1s on Fedora: install `qt6-qtwebengine-freeworld` from RPM Fusion (stock WebEngine lacks proprietary codecs). The app passes `--widevine-cdm-path` automatically; check Diagnostics for the CDM in use.
- Incompatible CDM: check ELF arch with file command.
- Login loops: clear site data via Settings menu.
- Audio failures: check PipeWire/PulseAudio.
- Renderer crashes: check logs in ~/.local/state/amazon-music-desktop/logs.
