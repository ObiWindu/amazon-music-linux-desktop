# Widevine CDM per distribution

The application does not bundle the proprietary Widevine CDM. Each distro package
recommends the system-provided CDM:

- Fedora: widevine-installer (provides /var/lib/widevine)
- Debian/Ubuntu: chromium-widevine or google-chrome (provides WidevineCdm)
- Arch: chromium-widevine (AUR) or google-chrome

The app's `ensure_widevine_user_dir()` sets up ~/.config/chromium/WidevineCdm
and ~/.config/google-chrome/WidevineCdm on first run, pointing at the newest
CDM it can find. Component-updated builds under
`~/.config/<app>/WidevineCdm/<version>/` (for example from Chrome, Chromium,
or an Electron application) are preferred over the older distro package.
