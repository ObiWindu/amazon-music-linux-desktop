from amazon_music_desktop.services.logging_service import redact_text, sanitize_url


def test_redact_password():
    out = redact_text("password=secret123")
    assert "secret123" not in out


def test_redact_token():
    out = redact_text("token=abc.def")
    assert "abc.def" not in out


def test_sanitize_url_strips_query():
    url = "https://music.amazon.fr/?token=secret&x=1"
    out = sanitize_url(url)
    assert "token" not in out
    assert "secret" not in out
