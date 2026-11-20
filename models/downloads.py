"""Helpers para reconocer descargas existentes por nombre de archivo."""
import os
import re
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


# Palabras que solo describen el formato o la publicación del video, no la canción.
# Una etiqueta entre paréntesis/corchetes se ignora SOLO si todas sus palabras están
# en esta lista; si trae cualquier otra ("Remix", "Live", "Cover", "feat. X",
# "Acoustic", "Instrumental"...), forma parte del nombre y se conserva.
_NOISE_WORDS = frozenset({
    'official', 'oficial', 'video', 'videoclip', 'clip', 'music', 'musical', 'mv',
    'audio', 'lyric', 'lyrics', 'letra', 'letras', 'visualizer', 'visualiser',
    'hd', 'hq', 'uhd', 'full', 'vevo', 'sub', 'subs', 'subtitulado', 'subtitulada',
    'subtitulos', 'subtitles', 'with', 'con',
})
_NOISE_RESOLUTION = re.compile(r'\d{3,4}p|\d{1,2}k|\d{2,3}fps')
_BRACKETS = re.compile(r'\([^()]*\)|\[[^\[\]]*\]|\{[^{}]*\}|【[^】]*】|「[^」]*」|『[^』]*』')
# "Artista - Canción - Official Video": quita el último tramo si solo es relleno.
_TRAILING_SEGMENT = re.compile(r'^(?P<head>.*\S)\s+[-–—|:_/·•]\s+(?P<tail>[^-–—|:_/·•]*)$')


# Marcas técnicas sueltas al final ("Canción HD") que no pueden ser parte del título.
_TRAILING_TECH = re.compile(r'\s+(?:hd|hq|uhd|\d{3,4}p|\d{1,2}k|\d{2,3}fps)$', re.IGNORECASE)


def _words(text):
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c)).casefold()
    return re.findall(r'[^\W_]+', text)


def _is_noise(text):
    words = _words(text)
    return bool(words) and all(
        w in _NOISE_WORDS or _NOISE_RESOLUTION.fullmatch(w) for w in words)


def _strip_noise(text):
    """Quita etiquetas de relleno como "(Official Video)" o "[Lyrics]" y un tramo
    final tipo " - Official Audio". El artista y las variantes (Remix, Live...) se
    conservan, así que canciones de autores distintos no se confunden."""
    text = _BRACKETS.sub(lambda m: '' if _is_noise(m.group(0)[1:-1]) else m.group(0), text)
    text = re.sub(r'\s+', ' ', text).strip()
    while True:
        text = _TRAILING_TECH.sub('', text).strip()
        m = _TRAILING_SEGMENT.match(text)
        if not (m and _is_noise(m.group('tail'))):
            break
        text = m.group('head').strip()
    return text


def _fold(text):
    text = unicodedata.normalize('NFKC', text)
    return re.sub(r'\s+', ' ', text).strip(' .-_').casefold()


def download_name_key(name):
    """Clave de comparación de un título o nombre de archivo.

    Se normaliza como lo hace yt-dlp al guardar el archivo y se ignora el relleno
    ("Official Video", "Official Audio", "Lyrics", "HD"...), de modo que dos versiones
    de la misma canción coinciden. "Remix", "Live" o un artista distinto en el título
    dan una clave diferente."""
    # Importar al usarlo permite que services.py active la versión actualizada
    # de yt-dlp antes de que este módulo se cargue.
    from yt_dlp.utils import sanitize_filename

    safe_name = sanitize_filename(str(name)).strip().rstrip('. ')
    safe_name = safe_name[:_MAX_TITLE_LENGTH].rstrip('. ')
    full = _fold(safe_name)
    # Si el título es solo relleno (p. ej. "(Official Video)"), se usa completo.
    return _fold(_strip_noise(unicodedata.normalize('NFKC', safe_name))) or full


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
