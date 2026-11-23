import pytest

from models import workers
from models.workers import DownloadThread


def _options_for(monkeypatch, fmt, embed_meta=True, ffmpeg='/usr/bin/ffmpeg'):
    """Ejecuta DownloadThread.run() sin red y devuelve las opciones de yt-dlp."""
    captured = {}
    monkeypatch.setattr(workers, 'find_ffmpeg', lambda: ffmpeg)
    monkeypatch.setattr(workers, 'get_cookie_option', lambda: {})
    monkeypatch.setattr(
        workers, 'run_with_auth_fallback',
        lambda base, action, allow_browser_cookies=False: captured.update(base))
    DownloadThread('t', 'https://x/v', fmt, 'best', '/tmp', 192, 0, True,
                   False, embed_meta=embed_meta).run()
    return captured


def _keys(opts):
    return [pp['key'] for pp in opts.get('postprocessors', [])]


def test_mp3_embeds_metadata_and_cover(monkeypatch):
    opts = _options_for(monkeypatch, 'mp3')
    assert opts['writethumbnail'] is True
    assert _keys(opts) == ['FFmpegExtractAudio', 'FFmpegThumbnailsConvertor',
                           'FFmpegMetadata', 'EmbedThumbnail']
    convertor = opts['postprocessors'][1]
    assert convertor['format'] == 'jpg' and convertor['when'] == 'before_dl'


def test_mp3_without_embed_keeps_only_conversion(monkeypatch):
    opts = _options_for(monkeypatch, 'mp3', embed_meta=False)
    assert 'writethumbnail' not in opts
    assert _keys(opts) == ['FFmpegExtractAudio']


@pytest.mark.parametrize('fmt', ['mp4', 'm4a', 'opus'])
def test_other_formats_are_not_touched(monkeypatch, fmt):
    opts = _options_for(monkeypatch, fmt)
    assert 'EmbedThumbnail' not in _keys(opts)
    assert 'writethumbnail' not in opts


def test_mp3_without_ffmpeg_does_not_try_to_embed(monkeypatch):
    opts = _options_for(monkeypatch, 'mp3', ffmpeg=None)
    assert 'EmbedThumbnail' not in _keys(opts)


@pytest.mark.parametrize('speed, eta, expected', [
    (2 * 1024 ** 2, 75, '2.0 MB/s  ·  1:15 restante'),
    (512 * 1024, 3725, '512.0 KB/s  ·  1:02:05 restante'),
    (800, None, '800 B/s'),
    (0, 30, ''),
])
def test_speed_text_includes_eta(speed, eta, expected):
    assert DownloadThread._fmt_speed(speed, eta) == expected


def test_entry_thumbnail_prefers_size_close_to_250():
    from models.workers import entry_thumbnail
    e = {'thumbnails': [{'url': 'small', 'width': 120}, {'url': 'mid', 'width': 246},
                        {'url': 'big', 'width': 1280}]}
    assert entry_thumbnail(e) == 'mid'


def test_entry_thumbnail_falls_back_to_youtube_id():
    from models.workers import entry_thumbnail
    assert entry_thumbnail({'id': 'abc123', 'url': 'https://youtu.be/abc123'}) \
        == 'https://i.ytimg.com/vi/abc123/mqdefault.jpg'
    assert entry_thumbnail({'id': 'x', 'url': 'https://tiktok.com/x'}) == ''
