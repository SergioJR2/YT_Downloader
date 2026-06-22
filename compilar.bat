@echo off
cd /d "%~dp0"
title YT Downloader - Compilador
color 0A

echo.
echo  ============================================
echo   YT Downloader ESCRITORIO - Generador .EXE
echo  ============================================
echo.

echo  [1/3] Instalando dependencias...
python -m pip install pyinstaller PyQt6 yt-dlp --quiet
if errorlevel 1 (
    echo  ERROR: Fallo al instalar dependencias.
    pause & exit /b 1
)

echo  [2/3] Compilando .exe (puede tardar 3-6 minutos)...
echo.
python -m PyInstaller YT_Downloader.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo  ERROR: Fallo al compilar.
    pause & exit /b 1
)

echo.
echo  [3/3] Limpiando temporales...
rmdir /s /q build 2>nul

echo.
echo  ============================================
echo   LISTO!  dist\YT_Downloader.exe
echo  ============================================
echo.
pause
