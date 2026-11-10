"""Rutas y valores por defecto de la aplicación."""
import os

APP_NAME = "YT Downloader"
LIBS_ROOT = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_NAME.replace(" ", "_"))
LIBS_META = os.path.join(LIBS_ROOT, "libs_meta.json")
DENO_DIR = os.path.join(LIBS_ROOT, "deno")
JS_RUNTIMES = ("deno", "node", "bun", "quickjs")
_JS_BINARY = {"deno": "deno", "node": "node", "bun": "bun", "quickjs": "qjs"}
BROWSERS = ("firefox", "edge", "chrome", "brave")
ALT_CLIENTS = ("default", "tv", "web_safari", "mweb")

DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Descargas_YouTube")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DEFAULT_CONCURRENT = 2
MAX_CONCURRENT = 5
LOCK_RETRIES = 4
LOCK_RETRY_DELAY = 2
