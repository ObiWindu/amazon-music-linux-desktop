# Architecture

Modules:
- app.py: startup/shutdown
- main_window.py: UI and browser view
- browser/profile.py: persistent WebEngine profile
- browser/navigation.py: origin policy
- browser/download_policy.py: download validation
- browser/drm_diagnostics.py: Widevine checks
- services/configuration.py: validated config
- services/logging_service.py: redacted logging
- ui/*: dialogs

Data locations:
- Config: ~/.config/amazon-music-desktop
- Profile: ~/.local/share/amazon-music-desktop
- Cache: ~/.cache/amazon-music-desktop
- Logs: ~/.local/state/amazon-music-desktop/logs
