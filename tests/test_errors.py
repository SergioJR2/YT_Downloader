import pytest

from models import errors, services
from models.errors import clean_err, is_webpage_blocked_error

TIKTOK = RuntimeError("ERROR: [TikTok] 769: Unexpected response from webpage request; "
                      "please report this issue")


def test_tiktok_blocked_error_is_recognised():
    assert is_webpage_blocked_error(TIKTOK)
    assert not is_webpage_blocked_error(RuntimeError("Video unavailable"))


def test_hint_asks_for_curl_cffi_when_missing(monkeypatch):
    monkeypatch.setattr(errors, 'has_impersonation', lambda: False)
    assert 'curl-cffi' in clean_err(TIKTOK)


def test_hint_suggests_update_or_cookies_when_curl_cffi_present(monkeypatch):
    monkeypatch.setattr(errors, 'has_impersonation', lambda: True)
    msg = clean_err(TIKTOK)
    assert 'curl-cffi' not in msg and 'cookies.txt' in msg


def test_blocked_error_retries_with_cookies_file(monkeypatch):
    """Antes solo los errores de YouTube probaban cookies; ahora también este."""
    used = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(services.yt_dlp, 'YoutubeDL', FakeYDL)

    def action(ydl):
        used.append('cookiefile' in ydl.opts)
        if 'cookiefile' not in ydl.opts:
            raise TIKTOK
        return 'ok'

    assert services.run_with_auth_fallback({'cookiefile': 'c.txt'}, action) == 'ok'
    assert used[0] is False and used[-1] is True


def test_unrelated_error_is_not_retried(monkeypatch):
    calls = []

    class FakeYDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(services.yt_dlp, 'YoutubeDL', FakeYDL)

    def action(ydl):
        calls.append(1)
        raise RuntimeError("HTTP Error 500")

    with pytest.raises(RuntimeError):
        services.run_with_auth_fallback({'cookiefile': 'c.txt'}, action)
    assert len(calls) == 1
