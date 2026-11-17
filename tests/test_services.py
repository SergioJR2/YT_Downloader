import pytest

pytest.importorskip("yt_dlp")

from models import services


def test_ver_tuple_orders_dates_correctly():
    assert services._ver_tuple("2025.11.12") > services._ver_tuple("2025.9.30")
    assert services._ver_tuple(None) == ()


def test_browser_cookies_are_opt_in(monkeypatch):
    """Sin consentimiento, nunca se intenta leer cookies del navegador."""
    tried = []

    class FakeYDL:
        def __init__(self, opts):
            tried.append(opts)
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def action(ydl):
        raise Exception("Sign in to confirm you're not a bot")

    monkeypatch.setattr(services.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(services, "youtube_opts", lambda: {})

    services.set_browser_cookies(False)
    with pytest.raises(Exception):
        services.run_with_auth_fallback({}, action)
    assert not any("cookiesfrombrowser" in o for o in tried)

    tried.clear()
    services.set_browser_cookies(True)
    with pytest.raises(Exception):
        services.run_with_auth_fallback({}, action)
    services.set_browser_cookies(False)
    assert any("cookiesfrombrowser" in o for o in tried)
