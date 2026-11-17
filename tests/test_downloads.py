import pytest

pytest.importorskip("yt_dlp")

from models.downloads import download_name_key, existing_download_names


def test_name_key_is_case_and_unicode_insensitive():
    assert download_name_key("Canción  ") == download_name_key("canción")
    assert download_name_key("Cafe\u0301") == download_name_key("Caf\u00e9")


def test_name_key_truncates_long_titles():
    long = "a" * 400
    assert len(download_name_key(long)) == 150


def test_existing_names_split_audio_and_video(tmp_path):
    (tmp_path / "Tema.mp3").write_bytes(b"")
    (tmp_path / "Clip.mp4").write_bytes(b"")
    (tmp_path / "Pendiente.mp4.part").write_bytes(b"")
    (tmp_path / "notas.txt").write_bytes(b"")
    audio = existing_download_names(str(tmp_path), "audio")
    video = existing_download_names(str(tmp_path), "video")
    assert set(audio) == {download_name_key("Tema")}
    assert set(video) == {download_name_key("Clip")}


def test_mp3_does_not_block_mp4_with_same_name(tmp_path):
    (tmp_path / "Titulo.mp3").write_bytes(b"")
    key = download_name_key("Titulo")
    assert key in existing_download_names(str(tmp_path), "audio")
    assert key not in existing_download_names(str(tmp_path), "video")
