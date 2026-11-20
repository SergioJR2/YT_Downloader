"""Rutas y valores por defecto de la aplicación."""
import os

APP_NAME = "YT Downloader"
# Versión de ESTE código. Súbela en cada release (debe coincidir con el tag de GitHub,
# p. ej. tag V1.3.0 -> "1.3.0"). compilar.bat la pasa también al instalador.
APP_VERSION = "1.5.0"
GITHUB_REPO = "SergioJR2/YT_Downloader"
LIBS_ROOT = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_NAME.replace(" ", "_"))
LIBS_META = os.path.join(LIBS_ROOT, "libs_meta.json")
DENO_DIR = os.path.join(LIBS_ROOT, "deno")
UPDATE_DIR = os.path.join(LIBS_ROOT, "updates")
LOG_FILE = os.path.join(LIBS_ROOT, "yt_downloader.log")
# Deno se instala con versión FIJA y SHA-256 incluido aquí (independiente del servidor
# de descarga). Para subir de versión: cambia DENO_VERSION y los dos hashes
# (se publican en <release>/deno-<arch>-pc-windows-msvc.zip.sha256sum).
DENO_VERSION = "v2.9.8"
DENO_SHA256 = {
    "x86_64":  "cba84b26e0df5ae7f74fc66b86a95b866872a86292ebd84fa1e959927edd93bf",
    "aarch64": "b413b92b735b50c198e8fe3b85af1aa50e29d5f72e229aab701d132286e14cef",
}
JS_RUNTIMES = ("deno", "node", "bun", "quickjs")
_JS_BINARY = {"deno": "deno", "node": "node", "bun": "bun", "quickjs": "qjs"}
BROWSERS = ("firefox", "edge", "chrome", "brave")
ALT_CLIENTS = ("default", "tv", "web_safari", "mweb")

DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Descargas_YouTube")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

PLAYLIST_PAGE = 200     # filas que se muestran de una vez en una playlist
PLAYLIST_MAX = 1000     # máximo de videos que se cargan de una playlist

DEFAULT_CONCURRENT = 2
MAX_CONCURRENT = 5
LOCK_RETRIES = 4
LOCK_RETRY_DELAY = 2
