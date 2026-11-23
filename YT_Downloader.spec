# -*- mode: python ; coding: utf-8 -*-
import os
import sysconfig
from PyInstaller.utils.hooks import collect_all

# Evita que bindepend resuelva dependencias de Qt contra DLL de otros runtimes
# que aparezcan antes en PATH (por ejemplo, ICU de Poppler/Codex). En esta
# máquina eso empaquetaba un icuuc.dll incompatible y QtWidgets no arrancaba.
QT_BIN = os.path.join(sysconfig.get_paths()['purelib'], 'PyQt6', 'Qt6', 'bin')
WINDOWS_SYSTEM32 = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
_existing_path = os.environ.get('PATH', '')
os.environ['PATH'] = os.pathsep.join(
    path for path in (QT_BIN, WINDOWS_SYSTEM32, _existing_path) if path
)

# compilar.bat define YT_INCLUDE_FFMPEG:  1 = Completo (con ffmpeg), 0 = Ligero.
# Si se compila sin el .bat, el valor por defecto es "completo".
INCLUDE_FFMPEG = os.environ.get('YT_INCLUDE_FFMPEG', '1') == '1'

yt_datas, yt_bins, yt_hidden = collect_all('yt_dlp')
# Solver JavaScript de YouTube (imprescindible desde yt-dlp 2025.11)
ej_datas, ej_bins, ej_hidden = collect_all('yt_dlp_ejs')
psutil_datas, psutil_bins, psutil_hidden = collect_all('psutil')
# curl_cffi: permite a yt-dlp "imitar" un navegador (TikTok lo exige; sin él
# responde "Unexpected response from webpage request").
cc_datas, cc_bins, cc_hidden = [], [], []
try:
    cc_datas, cc_bins, cc_hidden = collect_all('curl_cffi')
except Exception:
    print('AVISO: curl-cffi no esta instalado; TikTok no funcionara en este .exe.')
excludes = ['tkinter', 'matplotlib', 'numpy', 'flask', 'scipy']

# ffmpeg: solo en la version "Completa" (binario de imageio-ffmpeg)
io_datas, io_bins, io_hidden = [], [], []
if INCLUDE_FFMPEG:
    try:
        io_datas, io_bins, io_hidden = collect_all('imageio_ffmpeg')
    except Exception:
        pass
    if not (io_datas or io_bins):
        print('AVISO: imageio-ffmpeg no esta instalado; el .exe saldra sin ffmpeg.')
else:
    excludes.append('imageio_ffmpeg')   # version Ligera: sin ffmpeg

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[*yt_bins, *ej_bins, *psutil_bins, *io_bins, *cc_bins],
    datas=[*yt_datas, *ej_datas, *psutil_datas, *io_datas, *cc_datas],
    hiddenimports=[
        *yt_hidden,
        *ej_hidden,
        *psutil_hidden,
        *io_hidden,
        *cc_hidden,
        'PyQt6.QtNetwork',
        'PyQt6.sip',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# PyInstaller can resolve Windows API-set shims and ICU DLLs from unrelated
# PATH entries. Keep API-set DLLs in Windows, and only keep ICU DLLs shipped
# inside PyQt6's Qt directory; a foreign icuuc.dll can make QtWidgets fail to load.
_qt_bin_normalized = os.path.normcase(os.path.abspath(QT_BIN))
a.binaries = [
    entry for entry in a.binaries
    if not (
        os.path.basename(entry[0]).lower().startswith(('api-ms-win-', 'ext-ms-win-'))
        or os.path.basename(entry[0]).lower() == 'ucrtbase.dll'
        or (
            os.path.basename(entry[0]).lower().startswith('icu')
            and not os.path.normcase(os.path.abspath(entry[1])).startswith(
                _qt_bin_normalized + os.sep
            )
        )
    )
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='YT_Downloader',
    debug=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # Sin consola negra al abrir
    icon='icon.ico',
)
