@echo off
cd /d "%~dp0"
title YT Downloader - Compilador
color 0A

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   YT Downloader — Generador de .EXE     ║
echo  ╚══════════════════════════════════════════╝
echo.

REM ── Verificar que las dependencias estén instaladas ───────────────────────
echo  [*] Verificando dependencias...
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] PyInstaller no encontrado.
    echo      Ejecuta primero:  instalar_dependencias.bat
    echo.
    pause & exit /b 1
)
python -m pip show PyQt6 >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] PyQt6 no encontrado.
    echo      Ejecuta primero:  instalar_dependencias.bat
    echo.
    pause & exit /b 1
)
echo      Dependencias OK.
echo.

REM ── Limpiar compilaciones anteriores ─────────────────────────────────────
echo  [*] Limpiando builds anteriores...
if exist build   rmdir /s /q build
if exist dist    rmdir /s /q dist
echo      Listo.
echo.

REM ── Compilar ──────────────────────────────────────────────────────────────
echo  [*] Compilando .exe (puede tardar 3-6 minutos)...
echo      No cierres esta ventana.
echo.
python -m PyInstaller YT_Downloader.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo  ╔══════════════════════════════════════════╗
    echo  ║   ERROR: Fallo al compilar.              ║
    echo  ║   Revisa los mensajes de arriba.         ║
    echo  ╚══════════════════════════════════════════╝
    echo.
    pause & exit /b 1
)

REM ── Limpiar temporales ────────────────────────────────────────────────────
echo.
echo  [*] Limpiando archivos temporales...
if exist build rmdir /s /q build
echo      Listo.
echo.

REM ── Verificar que el .exe existe ─────────────────────────────────────────
if not exist "dist\YT_Downloader.exe" (
    echo  [!] No se encontro el .exe en dist\. Algo salio mal.
    pause & exit /b 1
)

echo  ╔══════════════════════════════════════════╗
echo  ║   COMPILACION EXITOSA                    ║
echo  ║                                          ║
echo  ║   Archivo:  dist\YT_Downloader.exe       ║
echo  ║                                          ║
echo  ║   Puedes mover ese .exe a cualquier      ║
echo  ║   carpeta o escritorio y ejecutarlo.     ║
echo  ╚══════════════════════════════════════════╝
echo.

REM ── Abrir carpeta dist automáticamente ───────────────────────────────────
explorer dist
pause
