# DRM Compatibility

- Qt WebEngine: 6.11.2
- Chromium: 140.0.0.0
- CDM path: /var/lib/widevine/libwidevinecdm.so
- Architecture: aarch64 (ELF 64-bit)
- Dependencies: resolved (ldd)
- EME: com.widevine.alpha available (tested)
- CDM initialization: the app passes `--widevine-cdm-path=<cdm>` via `QTWEBENGINE_CHROMIUM_FLAGS` before engine init (system CDM preferred, user-level fallback). App also ensures the user-level WidevineCdm dir on startup.
- Fedora caveat: no `qt6-qtwebengine-freeworld` build is published for Fedora 44 aarch64; if protected playback fails, missing proprietary codecs in stock QtWebEngine is the likely cause.
- Amazon playback: requires valid account/subscription; not verified in this environment.
- Known limitation: Qt build hardcodes linux_x64 Widevine path; user-level symlink workaround used.
