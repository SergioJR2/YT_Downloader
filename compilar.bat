@echo off
cd /d "%~dp0"
title YT Downloader - Compilador
color 0A

echo.
echo  ============================================
echo   YT Downloader ESCRITORIO - Generador .EXE
echo  ============================================
echo.

echo  [1/4] Instalando dependencias...
python -m pip install -U pyinstaller PyQt6 "yt-dlp[default]" imageio-ffmpeg psutil --quiet
if errorlevel 1 (
    echo  ERROR: Fallo al instalar dependencias.
    pause & exit /b 1
)

echo  [2/4] Compilando .exe (puede tardar 3-6 minutos)...
echo.
echo  Elige el paquete para esta compilacion:
echo    L = Ligero, sin ffmpeg incluido (MP3 requiere ffmpeg instalado aparte)
echo    C = Completo, incluye ffmpeg para convertir a MP3
choice /C LC /N /M "Selecciona L o C: "
if errorlevel 2 (set "YT_INCLUDE_FFMPEG=1") else (set "YT_INCLUDE_FFMPEG=0")
if not exist "YT_Downloader.spec" (
    echo.
    echo  ERROR: No se encuentra YT_Downloader.spec en esta carpeta.
    echo  Restauralo desde el repositorio ^(git checkout YT_Downloader.spec^) o descargalo de nuevo.
    pause & exit /b 1
)
python -m PyInstaller YT_Downloader.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo  ERROR: Fallo al compilar.
    pause & exit /b 1
)

echo.
echo  [3/4] Limpiando temporales...
rmdir /s /q build 2>nul

echo.
echo  [4/4] Creando instalador (Setup)...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
set "APPVER="
for /f "delims=" %%v in ('python -c "from models.config import APP_VERSION; print(APP_VERSION)"') do set "APPVER=%%v"
if not defined APPVER (
    echo  ERROR: No se pudo leer APP_VERSION de models\config.py.
    pause & exit /b 1
)
if defined ISCC (
    "%ISCC%" /DAppVersion=%APPVER% instalador.iss
    if errorlevel 1 (
        echo  ERROR: Fallo al crear el instalador.
    ) else (
        echo.
        echo  Instalador listo: instalador\YT_Downloader_Setup.exe
    )
) else (
    echo  Inno Setup no esta instalado: se omite el instalador.
    echo  Para crearlo instala Inno Setup 6 ^(winget install JRSoftware.InnoSetup^)
    echo  y ejecuta compilar.bat otra vez.
)

echo.
echo  ============================================
echo   LISTO!  dist\YT_Downloader.exe
echo  ============================================
echo.
pause
