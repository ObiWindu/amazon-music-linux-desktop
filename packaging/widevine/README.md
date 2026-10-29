# Widevine CDM per distribution

The application does not bundle the proprietary Widevine CDM. Each distro package
recommends the system-provided CDM:

- Fedora: widevine-installer (provides /var/lib/widevine)
- Debian/Ubuntu: chromium-widevine or google-chrome (provides WidevineCdm)
- Arch: chromium-widevine (AUR) or google-chrome

The app's `ensure_widevine_user_dir()` sets up ~/.config/chromium/WidevineCdm
pointing to the system CDM on first run.
