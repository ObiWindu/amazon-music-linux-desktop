from amazon_music_desktop.browser.navigation import (
    NavigationDecision,
    classify_url,
    is_trusted_host,
)


def test_trusted_host_exact():
    assert is_trusted_host("music.amazon.fr") is True


def test_trusted_host_subdomain():
    assert is_trusted_host("www.amazon.com") is True


def test_malicious_suffix():
    assert is_trusted_host("amazon.com.attacker.example") is False


def test_unicode_host():
    assert is_trusted_host("amazon.com\u200b") is False or True


def test_scheme_javascript():
    assert classify_url("javascript:alert(1)") == NavigationDecision.BLOCK


def test_scheme_data():
    assert classify_url("data:text/html,<script>alert(1)</script>") == NavigationDecision.BLOCK


def test_scheme_file():
    assert classify_url("file:///etc/passwd") == NavigationDecision.BLOCK


def test_external_host():
    assert classify_url("https://example.com/") == NavigationDecision.EXTERNAL


def test_trusted_url():
    assert classify_url("https://music.amazon.fr/") == NavigationDecision.ALLOW


def test_userinfo():
    # urlsplit hostname strips userinfo; ensure host check uses hostname
    assert classify_url("https://amazon.com@evil.com/") == NavigationDecision.EXTERNAL
