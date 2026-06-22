@echo off
cd /d "%~dp0"
title YT Downloader - Instalador de Dependencias
color 0B

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   YT Downloader — Instalador             ║
echo  ║   Dependencias Python + ffmpeg           ║
echo  ╚══════════════════════════════════════════╝
echo.

REM ── Verificar Python ──────────────────────────────────────────────────────
echo  [*] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Python no encontrado.
    echo      Descargalo desde: https://www.python.org/downloads/
    echo      Asegurate de marcar "Add Python to PATH" al instalar.
    echo.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo      Encontrado: %%v
echo.

REM ── Verificar / instalar ffmpeg ───────────────────────────────────────────
echo  [*] Verificando ffmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo      ffmpeg no encontrado. Intentando instalar con winget...
    winget install --id Gyan.FFmpeg -e --silent
    if errorlevel 1 (
        echo.
        echo  [!] No se pudo instalar ffmpeg automaticamente.
        echo      Instalalo manualmente:  winget install ffmpeg
        echo      O descargalo de:        https://ffmpeg.org/download.html
        echo      y agrega la carpeta bin a tu PATH.
        echo.
        echo      Sin ffmpeg solo podras descargar video MP4.
        echo      La conversion a MP3 no estara disponible.
        echo.
    ) else (
        echo      ffmpeg instalado correctamente.
    )
) else (
    echo      ffmpeg ya esta instalado.
)
echo.

REM ── Instalar paquetes Python ──────────────────────────────────────────────
echo  [*] Actualizando pip...
python -m pip install --upgrade pip --quiet

echo  [*] Instalando PyQt6...
python -m pip install PyQt6 --quiet
if errorlevel 1 ( echo  [!] Error instalando PyQt6. & pause & exit /b 1 )
echo      PyQt6 listo.

echo  [*] Instalando yt-dlp...
python -m pip install yt-dlp --quiet
if errorlevel 1 ( echo  [!] Error instalando yt-dlp. & pause & exit /b 1 )
echo      yt-dlp listo.

echo  [*] Instalando PyInstaller...
python -m pip install pyinstaller --quiet
if errorlevel 1 ( echo  [!] Error instalando PyInstaller. & pause & exit /b 1 )
echo      PyInstaller listo.
echo.

echo  ╔══════════════════════════════════════════╗
echo  ║   Todas las dependencias instaladas.     ║
echo  ║   Ya puedes ejecutar compilar.bat        ║
echo  ╚══════════════════════════════════════════╝
echo.
pause
