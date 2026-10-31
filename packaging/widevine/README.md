# Widevine CDM per distribution

The default application package does not bundle the proprietary Widevine CDM.
Each distro package recommends the system-provided CDM:

- Fedora: widevine-installer (provides /var/lib/widevine)
- Debian/Ubuntu: chromium-widevine or google-chrome (provides WidevineCdm)
- Arch: chromium-widevine (AUR) or google-chrome

The app's `ensure_widevine_user_dir()` sets up ~/.config/chromium/WidevineCdm
and ~/.config/google-chrome/WidevineCdm on first run, pointing at the newest
CDM it can find. Component-updated builds under
`~/.config/<app>/WidevineCdm/<version>/` (for example from Chrome, Chromium,
or an Electron application) are preferred over the older distro package.
Note: on engine builds that ignore `--widevine-cdm-path` (Fedora's
qt6-qtwebengine 6.11.2, verified 2026-10-31), selection is recorded but
ineffective — the engine loads only its hardcoded distro path. See
`docs/DRM_COMPATIBILITY.md` and Diagnostics → Engine default CDM path.

## Optional local bundling

A private RPM can embed an already-installed CDM so the package does not depend
on a user-level Chromium profile:

```
rpmbuild -ba \
  --define '_topdir /tmp/rpmbuild' \
  --define 'bundled_cdm /path/to/WidevineCdm/<version>/_platform_specific/linux_arm64/libwidevinecdm.so' \
  packaging/rpm/amazon-music-desktop.spec
```

The resulting package is `aarch64` and installs the library, manifest, and
license under `/usr/lib64/amazon-music-desktop/WidevineCdm/`. The app discovers
that directory automatically and still prefers a newer user-level CDM if one
exists.

**Do not redistribute a bundled build.** Google's Widevine license states that
the CDM may not be used, modified, sold, or distributed without a separate
license agreement. Keep the package local; the default `noarch` RPM remains
free of proprietary files.
