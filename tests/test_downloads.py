import pytest

from models.downloads import download_name_key as key, existing_download_names


@pytest.mark.parametrize("a, b, same", [
    ("Artista - Canción (Official Video)", "Artista - Canción (Official Audio)", True),
    ("Artista - Canción | Official Video", "Artista - Canción [Audio Oficial] HD", True),
    ("Artista - Canción - Official Music Video", "Artista - Canción (Lyrics) [4K]", True),
    ("Artista - Canción (Video Oficial)", "Artista - Canción", True),
    ("Artista - Canción (Official Video)", "Artista - Canción (Remix)", False),
    ("Artista - Canción", "Artista - Canción (Live)", False),
    ("Artista - Canción", "Artista - Canción (feat. Otro)", False),
    ("Artista - Canción (Acoustic Version)", "Artista - Canción (Official Audio)", False),
    ("Artista A - Canción (Official Video)", "Artista B - Canción (Official Video)", False),
    ("Video Killed the Radio Star", "Killed the Radio Star", False),
])
def test_name_key(a, b, same):
    assert (key(a) == key(b)) is same


def test_title_made_only_of_noise_keeps_a_key():
    assert key("(Official Video)")


def test_existing_names_walks_subfolders_and_ignores_hidden(tmp_path):
    (tmp_path / "Artista - Canción (Official Audio).mp3").touch()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "Otro - Tema [Lyrics].m4a").touch()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "Oculto.mp3").touch()
    (tmp_path / "Parcial.mp3.part").touch()
    (tmp_path / "Video.mp4").touch()

    found = existing_download_names(str(tmp_path), "audio")
    assert key("Artista - Canción (Official Video)") in found
    assert key("Otro - Tema") in found
    assert key("Oculto") not in found
    assert key("Parcial") not in found
    assert key("Video") not in found          # un mp4 no cuenta como audio


def test_parse_url_list_ignores_comments_blanks_and_duplicates():
    from models.downloads import parse_url_list
    text = "\ufeff# mi lista\nhttps://a.com/1\n\n  https://a.com/2  \nhttps://a.com/1\nHTTP://b.com/3\n"
    urls, invalid = parse_url_list(text)
    assert urls == ["https://a.com/1", "https://a.com/2", "HTTP://b.com/3"]
    assert invalid == []


def test_parse_url_list_reports_lines_that_are_not_links():
    from models.downloads import parse_url_list
    urls, invalid = parse_url_list("https://a.com/1\nuna canción\nwww.sinesquema.com\n")
    assert urls == ["https://a.com/1"]
    assert invalid == ["una canción", "www.sinesquema.com"]
