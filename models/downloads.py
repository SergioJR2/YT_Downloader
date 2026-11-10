"""Helpers para reconocer descargas existentes por nombre de archivo."""
import os
import unicodedata

_INCOMPLETE_SUFFIXES = {'.part', '.ytdl', '.temp'}
_VIDEO_SUFFIXES = {
    '.mp4', '.mkv', '.webm', '.mov', '.avi', '.m4v', '.flv', '.wmv',
    '.3gp', '.ts', '.mpeg', '.mpg', '.ogv', '.m2ts', '.mts',
}
_AUDIO_SUFFIXES = {
    '.mp3', '.m4a', '.opus', '.ogg', '.oga', '.wav', '.flac', '.aac',
    '.wma', '.aiff', '.alac', '.mka', '.weba', '.webm',
}
_MAX_TITLE_LENGTH = 150  # coincide con trim_file_name en DownloadThread


def download_name_key(name):
    """Normaliza un título o nombre base como lo hace la salida de yt-dlp."""
    # Importar al usarlo permite que services.py active la versión actualizada
    # de yt-dlp antes de que este módulo se cargue.
    from yt_dlp.utils import sanitize_filename

    safe_name = sanitize_filename(str(name)).strip().rstrip('. ')
    safe_name = safe_name[:_MAX_TITLE_LENGTH].rstrip('. ')
    return unicodedata.normalize('NFC', safe_name).casefold()


def existing_download_names(folder, media_kind):
    """Devuelve nombres existentes del tipo de medio solicitado."""
    suffixes = _VIDEO_SUFFIXES if media_kind == 'video' else _AUDIO_SUFFIXES
    found = {}
    with os.scandir(folder) as entries:
        for entry in entries:
            if not entry.is_file():
                continue
            stem, extension = os.path.splitext(entry.name)
            if extension.casefold() in _INCOMPLETE_SUFFIXES:
                continue
            if extension.casefold() not in suffixes:
                continue
            key = download_name_key(stem)
            if key:
                found.setdefault(key, entry.name)
    return found
