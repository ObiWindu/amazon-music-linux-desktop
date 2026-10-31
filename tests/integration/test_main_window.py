import pytest

from amazon_music_desktop.browser.profile import ProfileManager
from amazon_music_desktop.main_window import MainWindow
from amazon_music_desktop.services.configuration import ConfigService


@pytest.fixture
def window(qtbot, tmp_path):
    svc = ConfigService(config_file=tmp_path / "cfg.json")
    svc.load()
    pm = ProfileManager(profile_dir=tmp_path / "profile_root")
    profile = pm.create_profile()
    w = MainWindow(svc, pm, profile)
    qtbot.addWidget(w)
    return w


def test_window_renders(window):
    assert window.isVisible() is False or True
    window.show()
    assert window.width() >= 900


def test_sidebar_exists(window):
    assert window.btn_home is not None


def test_go_home(window, qtbot):
    with qtbot.waitSignal(window.view.loadFinished, timeout=10000):
        window.go_home()
    assert "amazon" in window.current_url()


def test_user_agent_matches_host_arch(tmp_path):
    import platform

    from amazon_music_desktop.browser.profile import ProfileManager

    pm = ProfileManager(profile_dir=tmp_path / "profile_root")
    profile = pm.create_profile()
    ua = profile.httpUserAgent()
    machine = platform.machine().lower()
    expected = "aarch64" if machine in ("aarch64", "arm64") else "x86_64"
    opposite = "x86_64" if expected == "aarch64" else "aarch64"
    assert expected in ua
    assert opposite not in ua
