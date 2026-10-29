# Troubleshooting

- Missing WebEngine bindings: install qt6-qtwebengine and python3-pyside6.
- Missing CDM: install widevine-installer; check /var/lib/widevine.
- Incompatible CDM: check ELF arch with file command.
- Login loops: clear site data via Settings menu.
- Audio failures: check PipeWire/PulseAudio.
- Renderer crashes: check logs in ~/.local/state/amazon-music-desktop/logs.
