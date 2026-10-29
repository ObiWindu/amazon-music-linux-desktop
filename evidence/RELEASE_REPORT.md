# Release Report

- RPM: /tmp/opencode/rpmbuild/RPMS/noarch/amazon-music-desktop-0.1.0-1.fc44.noarch.rpm
- Bundled RPM (CDM-free): evidence/release/amazon-music-desktop-0.1.0-1.fc44.noarch.rpm
- Local bundled-CDM RPM (not tracked): evidence/release/amazon-music-desktop-0.1.0-1.fc44.aarch64.rpm
  - Contains Widevine CDM 4.10.3112.0 under `/usr/lib64/amazon-music-desktop/WidevineCdm/`.
  - Built with `--define 'bundled_cdm ...'`; the CDM is copied byte-for-byte (strip/brp disabled).
  - Do not redistribute: Google's Widevine license prohibits it.
- Rebuilt 2026-10-30 with newest-CDM discovery (4.10.3112.0 selected over the 2022 4.10.2662.3 system build).
- Source installed and importable from staging.
- Launcher: /usr/bin/amazon-music-desktop
