# DRM Compatibility

- Qt WebEngine: 6.11.2
- Chromium: 140.0.0.0
- CDM path: /var/lib/widevine/libwidevinecdm.so
- Architecture: aarch64 (ELF 64-bit)
- Dependencies: resolved (ldd)
- EME: com.widevine.alpha available (tested)
- CDM initialization: Qt WebEngine discovers Widevine via ~/.config/chromium/WidevineCdm (user-level) or system path. App ensures user-level dir on startup.
- Amazon playback: requires valid account/subscription; not verified in this environment.
- Known limitation: Qt build hardcodes linux_x64 Widevine path; user-level symlink workaround used.
