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
