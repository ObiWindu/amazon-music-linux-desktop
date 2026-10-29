from amazon_music_desktop.browser.navigation import (
    NavigationDecision,
    classify_url,
    is_trusted_host,
)


def test_evil_suffix():
    assert is_trusted_host("amazon.com.evil.com") is False


def test_subdomain_of_evil():
    assert is_trusted_host("x.amazon.com.evil.com") is False


def test_trusted_not_confused():
    assert is_trusted_host("notamazon.com") is False


def test_scheme_rejection():
    for u in ["javascript:alert(1)", "file:///etc/passwd", "ftp://x", "intent://x"]:
        assert classify_url(u) == NavigationDecision.BLOCK
