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


def _skip_dir(name):
    """Carpetas ocultas o de sistema que no contienen descargas."""
    return name.startswith(('.', '$')) or name.casefold() == 'system volume information'


def existing_download_names(folder, media_kind):
    """Devuelve los nombres existentes del tipo de medio solicitado, buscando
    también dentro de las subcarpetas.

    El valor de cada entrada es el nombre del archivo, o su ruta relativa a
    `folder` cuando está en una subcarpeta (para mostrarlo en los avisos)."""
    suffixes = _VIDEO_SUFFIXES if media_kind == 'video' else _AUDIO_SUFFIXES
    root = os.path.abspath(folder)

    def on_error(err):
        # Una subcarpeta ilegible se ignora; si falla la carpeta raíz, se informa.
        if os.path.normcase(os.path.abspath(err.filename or '')) == os.path.normcase(root):
            raise err

    found = {}
    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
        dirnames[:] = sorted(d for d in dirnames if not _skip_dir(d))
        rel_dir = os.path.relpath(dirpath, root)
        for name in sorted(filenames):
            stem, extension = os.path.splitext(name)
            if extension.casefold() in _INCOMPLETE_SUFFIXES:
                continue
            if extension.casefold() not in suffixes:
                continue
            key = download_name_key(stem)
            if key:
                shown = name if rel_dir == '.' else os.path.join(rel_dir, name)
                found.setdefault(key, shown)
    return found
