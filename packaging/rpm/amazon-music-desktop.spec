%global debug_package %{nil}

%if %{?bundled_cdm:1}%{!?bundled_cdm:0}
# The Widevine CDM is signed; strip/brp post-processing would alter it.
%global __os_install_post %{nil}
%endif

Name:           amazon-music-desktop
Version:        0.1.0
Release:        1%{?dist}
Summary:        Desktop client for Amazon Music
License:        %{?bundled_cdm:MIT AND Proprietary}%{!?bundled_cdm:MIT}
URL:            https://example.com/amazon-music-desktop
Source0:        %{name}-%{version}.tar.gz
# The default build is a clean noarch package. Defining bundled_cdm
# (a path to an installed libwidevinecdm.so) produces an aarch64 package
# with that CDM under <libdir>/amazon-music-desktop/WidevineCdm.
BuildArch:      %{?bundled_cdm:aarch64}%{!?bundled_cdm:noarch}
Requires:       python3
Requires:       python3-pyside6
Requires:       qt6-qtwebengine

%description
A native desktop wrapper for Amazon Music using Qt WebEngine.

%prep
%autosetup

%build
# nothing to build

%install
mkdir -p %{buildroot}/usr/lib/python3.*/site-packages 2>/dev/null || true
# install python package
mkdir -p %{buildroot}/usr/lib/python3.14/site-packages
cp -r src/amazon_music_desktop %{buildroot}/usr/lib/python3.14/site-packages/
# launcher
mkdir -p %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/amazon-music-desktop << 'EOF'
#!/usr/bin/env python3
import sys
from amazon_music_desktop.app import main
sys.exit(main())
EOF
chmod 755 %{buildroot}%{_bindir}/amazon-music-desktop
# desktop entry
mkdir -p %{buildroot}%{_datadir}/applications
install -m 644 packaging/desktop/amazon-music-desktop.desktop %{buildroot}%{_datadir}/applications/
# icon
mkdir -p %{buildroot}%{_datadir}/icons/hicolor/256x256/apps
install -m 644 packaging/icons/app.png %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/amazon-music-desktop.png

%if %{?bundled_cdm:1}%{!?bundled_cdm:0}
# Optional Widevine CDM for local-only builds. Do not redistribute the
# resulting package: Google's Widevine license prohibits it.
install -d %{buildroot}%{_libdir}/amazon-music-desktop/WidevineCdm/_platform_specific/linux_arm64
install -m 755 %{bundled_cdm} %{buildroot}%{_libdir}/amazon-music-desktop/WidevineCdm/_platform_specific/linux_arm64/libwidevinecdm.so
install -m 644 "$(dirname "$(dirname "$(dirname "%{bundled_cdm}")")")/manifest.json" %{buildroot}%{_libdir}/amazon-music-desktop/WidevineCdm/manifest.json
install -m 644 "$(dirname "$(dirname "$(dirname "%{bundled_cdm}")")")/LICENSE" %{buildroot}%{_libdir}/amazon-music-desktop/WidevineCdm/LICENSE
%endif

%files
%license LICENSE
%doc README.md
/usr/lib/python3.14/site-packages/amazon_music_desktop/
%{_bindir}/amazon-music-desktop
%{_datadir}/applications/amazon-music-desktop.desktop
%{_datadir}/icons/hicolor/256x256/apps/amazon-music-desktop.png
%if %{?bundled_cdm:1}%{!?bundled_cdm:0}
%{_libdir}/amazon-music-desktop/WidevineCdm/
%endif
