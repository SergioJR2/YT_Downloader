@echo off
cd /d "%~dp0"
title YT Downloader - Instalador de Dependencias
color 0B

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   YT Downloader — Instalador             ║
echo  ║   Dependencias Python (sin ffmpeg)       ║
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

REM ── Instalar paquetes Python ──────────────────────────────────────────────
echo  [*] Actualizando pip...
python -m pip install --upgrade pip --quiet

echo  [*] Instalando PyQt6...
python -m pip install PyQt6 --quiet
if errorlevel 1 ( echo  [!] Error instalando PyQt6. & pause & exit /b 1 )
echo      PyQt6 listo.

echo  [*] Instalando yt-dlp...
python -m pip install -U "yt-dlp[default]" --quiet
if errorlevel 1 ( echo  [!] Error instalando yt-dlp. & pause & exit /b 1 )
echo      yt-dlp listo.

echo  [*] Instalando imageio-ffmpeg (opcional, para MP3 real)...
python -m pip install imageio-ffmpeg --quiet
if errorlevel 1 ( echo      No se pudo instalar; se usara audio M4A. ) else ( echo      imageio-ffmpeg listo. )

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
