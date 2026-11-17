import pytest

from models.errors import (
    clean_err,
    is_bot_error,
    is_file_lock_error,
    is_http_416_error,
    is_unavailable_error,
)


@pytest.mark.parametrize("msg", [
    "ERROR: Sign in to confirm you're not a bot",
    "Sign in to confirm your age",
    "HTTP Error 403: Forbidden",
    "unable to download: 403 Forbidden",
])
def test_bot_errors_detected(msg):
    assert is_bot_error(Exception(msg))


@pytest.mark.parametrize("msg", [
    "Video unavailable",
    "https://youtube.com/watch?v=abc40399xyz no se pudo abrir",   # '403' dentro de un ID
    "Please sign in to your Google account",                        # 'sign in' suelto
])
def test_non_bot_errors_ignored(msg):
    assert not is_bot_error(Exception(msg))


def test_ansi_codes_and_error_prefix_are_removed():
    out = clean_err(Exception("\x1b[0;31mERROR:\x1b[0m ERROR: algo raro"))
    assert "\x1b" not in out and not out.startswith("ERROR")


def test_connection_errors_get_retry_hint():
    assert "Reintentar" in clean_err(Exception("Read timed out"))


def test_416_detection():
    assert is_http_416_error(Exception("HTTP Error 416: Requested range not satisfiable"))
    assert not is_http_416_error(Exception("HTTP Error 404"))


def test_file_lock_detection():
    assert is_file_lock_error(PermissionError("x"))
    assert is_file_lock_error(Exception("[WinError 5] Acceso denegado"))
    assert not is_file_lock_error(Exception("HTTP Error 404"))


def test_unavailable_detection():
    assert is_unavailable_error(Exception("Requested format is not available"))
    assert not is_unavailable_error(Exception("Read timed out"))


def test_bot_error_gets_cookies_hint():
    assert "cookies" in clean_err(Exception("Sign in to confirm you're not a bot")).lower()
