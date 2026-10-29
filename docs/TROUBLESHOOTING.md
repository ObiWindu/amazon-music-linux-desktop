# Troubleshooting

- Missing WebEngine bindings: install qt6-qtwebengine and python3-pyside6.
- Missing CDM: install widevine-installer; check /var/lib/widevine.
- Playback starts, then stops after ~1s: root cause confirmed with an instrumented live run. Sequence: EME session created, `generateRequest` OK, license POST to `music.amazon.fr/ZAZ/api/dmls/` → HTTP 400 `ForbiddenException`, `denialReason: VMP_VALIDATION_FAILED` ("UNVERIFIED request not eligible for LD content"), then the page empties the media element and retries once. Amazon validates the Widevine Verified Media Path; the only ARM64 Linux CDM (4.10.2662.3, 2022) fails that check. Server-side and unfixable from the app; codecs (AAC/MP3 verified) and the player UI are not involved.
- Native player buttons do nothing on the French page: fixed — controls now match fr + en labels ("Écouter", "Suivant", "Précédent", "aléatoire", "Répéter") plus data-testid hints, with carousel pagers ("Voir l'élément suivant/précédent…", "*PageButton") excluded; play/pause drives the page's media element directly, and `PlaybackRequiresUserGesture` is disabled so programmatic play() works.
- Playback errors after ~1s: the app passes `--widevine-cdm-path` automatically (check Diagnostics for the CDM in use). Run **Diagnostics → Test CDM session**: if session creation fails, the CDM is rejected by Chromium 140; if it succeeds (as observed), the failure is at license acquisition.
- The Amazon web player bar is never visible by design: the web view is docked so the page's bottom-docked player bar renders outside the visible window (`main_window._BrowserHost`). The page player is otherwise untouched — modifying its DOM/CSS correlated with playback teardowns. The native bottom bar drives it via clicks and mirrors its state via polling.
- Incompatible CDM: check ELF arch with file command.
- Login loops: clear site data via Settings menu.
- Audio failures: check PipeWire/PulseAudio.
- `ffmpeg not found` or unsupported-codec errors from `scripts/convert-to-mp3.sh`: on Fedora install the freeworld codec library from RPM Fusion free — `sudo dnf install ffmpeg libavcodec-freeworld` (stock Fedora uses `libavcodec-free`, which lacks some codecs).
- Renderer crashes: check logs in ~/.local/state/amazon-music-desktop/logs.
