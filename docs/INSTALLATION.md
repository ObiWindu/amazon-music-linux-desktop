# Installation

## Fedora Asahi Remix (AArch64)
```
sudo dnf install ./amazon-music-desktop-0.1.0-1.fc44.noarch.rpm
```

## Source
```
PYTHONPATH=src python3 -m amazon_music_desktop
```

## Private RPM with bundled Widevine
An aarch64 RPM built with `--define 'bundled_cdm <path>'` installs the CDM
under `/usr/lib64/amazon-music-desktop/WidevineCdm/`. The app discovers it
automatically. This build is for local use only; Google's Widevine license
prohibits redistribution. See `packaging/widevine/README.md` for the build
command.

## Uninstall
```
sudo dnf remove amazon-music-desktop
```
Profile data in ~/.local/share/amazon-music-desktop is preserved.
