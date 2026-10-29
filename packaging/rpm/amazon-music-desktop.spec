Name:           amazon-music-desktop
Version:        0.1.0
Release:        1%{?dist}
Summary:        Desktop client for Amazon Music
License:        MIT
URL:            https://example.com/amazon-music-desktop
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
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

%files
%license LICENSE
%doc README.md
/usr/lib/python3.14/site-packages/amazon_music_desktop/
%{_bindir}/amazon-music-desktop
%{_datadir}/applications/amazon-music-desktop.desktop
%{_datadir}/icons/hicolor/256x256/apps/amazon-music-desktop.png
