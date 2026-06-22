# YT Downloader 🎬

Aplicación de escritorio para Windows que descarga videos y audios de YouTube sin necesidad de abrir un navegador. Soporta videos individuales, playlists completas y conversión a MP3.

---

## Requisitos

| Requisito | Cómo obtenerlo |
|-----------|---------------|
| **Windows 10 / 11** | — |
| **Python 3.8 o superior** | [python.org/downloads](https://www.python.org/downloads/) — marcar ✅ *Add Python to PATH* |
| **ffmpeg** *(solo para MP3)* | `winget install ffmpeg` en la terminal |

> Si solo vas a descargar videos MP4, ffmpeg es opcional.

---

## Instalación y compilación

El proceso se divide en dos pasos con scripts separados:

### Paso 1 — Instalar dependencias
```
Doble clic en  instalar_dependencias.bat
```
Este script:
- Verifica que Python esté instalado
- Intenta instalar ffmpeg automáticamente con `winget`
- Instala PyQt6, yt-dlp y PyInstaller vía pip

Solo necesitas hacerlo **una vez** (o cuando actualices dependencias).

### Paso 2 — Compilar el .exe
```
Doble clic en  compilar.bat
```
Este script:
- Verifica que las dependencias del Paso 1 estén presentes
- Limpia compilaciones anteriores
- Genera el ejecutable en `dist\YT_Downloader.exe`
- Abre la carpeta `dist\` automáticamente al terminar

⏱️ La compilación tarda entre 3 y 6 minutos la primera vez.

---

## Uso

1. Abre `dist\YT_Downloader.exe` (puedes moverlo donde quieras)
2. Pega la URL de un video o playlist de YouTube
3. Haz clic en **Analizar**
4. Elige formato (MP4 o MP3) y calidad
5. Haz clic en **↓ Descargar**

Las descargas se guardan en:
```
C:\Users\TU_USUARIO\Descargas_YouTube\
```

### Descargar playlists

Cuando pegas una URL de playlist, la app muestra la lista completa de videos con checkboxes. Puedes:
- Seleccionar / deseleccionar videos individualmente
- Usar los botones **Todos**, **Ninguno** o **Invertir**
- Controlar cuántos videos se descargan a la vez (1–5) para no saturar la conexión

---

## Opciones de descarga

| Opción | Descripción |
|--------|-------------|
| **MP4 — Video** | Video con audio. Calidades: Mejor, 1080p, 720p, 480p |
| **MP3 — Audio** | Solo audio en 192 kbps. Requiere ffmpeg |
| **Descargas a la vez** | Cuántos videos de la playlist se descargan en paralelo (default: 2) |

> **Tip de rendimiento:** Si la computadora se pone lenta durante descargas de playlist, reduce "Descargas a la vez" a 1.

---

## Estructura del proyecto

```
YT_Downloader/
├── main.py                      ← Código fuente principal
├── YT_Downloader.spec           ← Configuración de PyInstaller
├── dependencias.bat    ← Paso 1: instalar todo lo necesario
├── compilar.bat                 ← Paso 2: generar el .exe
├── README.md                    ← Este archivo
└── dist/
    └── YT_Downloader.exe        ← Ejecutable generado (no incluido en repo)
```

---

## Solución de problemas

**"Python no encontrado"**
→ Reinstala Python desde [python.org](https://www.python.org/downloads/) marcando *Add Python to PATH*.

**"Error al instalar ffmpeg"**
→ Abre una terminal como administrador y ejecuta `winget install ffmpeg`. Si no tienes winget, descarga ffmpeg desde [ffmpeg.org](https://ffmpeg.org/download.html) y agrega la carpeta `bin` a tu variable de entorno PATH.

**"Error: Sign in to confirm you're not a bot"**
→ YouTube a veces bloquea descargas automatizadas. Espera unos minutos e intenta de nuevo. Si persiste, actualiza yt-dlp: `pip install -U yt-dlp`.

**El .exe no abre o da error de DLL**
→ Instala [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) de Microsoft.

**La descarga de MP3 falla**
→ Verifica que ffmpeg esté instalado: abre una terminal y escribe `ffmpeg -version`. Si no responde, sigue los pasos de instalación de ffmpeg arriba.

---

## Dependencias

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — motor de descarga
- [PyQt6](https://pypi.org/project/PyQt6/) — interfaz gráfica
- [PyInstaller](https://pyinstaller.org/) — empaquetado en .exe
- [ffmpeg](https://ffmpeg.org/) — conversión de audio