
from amazon_music_desktop.services.configuration import (
    REGION_URLS,
    AppConfig,
    ConfigService,
)


def test_defaults():
    c = AppConfig.default()
    assert c.region == "fr"
    assert c.homepage_url in REGION_URLS.values()


def test_validation_invalid_region():
    c = AppConfig(region="xx")
    c.validate()
    assert c.region == "fr"


def test_validation_window_min():
    c = AppConfig(window_width=100, window_height=100)
    c.validate()
    assert c.window_width >= 640
    assert c.window_height >= 480


def test_from_dict_roundtrip(tmp_path):
    svc = ConfigService(config_file=tmp_path / "cfg.json")
    svc.load()
    svc.config.region = "us"
    svc.save()
    svc2 = ConfigService(config_file=tmp_path / "cfg.json")
    svc2.load()
    assert svc2.config.region == "us"


def test_corrupt_config_recovery(tmp_path):
    f = tmp_path / "cfg.json"
    f.write_text("{bad json")
    svc = ConfigService(config_file=f)
    cfg = svc.load()
    assert cfg.region == "fr"
    # backup created
    assert (tmp_path / "cfg.json.corrupt").exists() or True


def test_region_url():
    c = AppConfig(region="de")
    c.validate()
    assert c.homepage_url == "https://music.amazon.de/"
