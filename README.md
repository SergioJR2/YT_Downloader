# YT Downloader 🎬

Aplicación de escritorio para Windows que descarga videos y audios de YouTube sin necesidad de abrir un navegador. Soporta videos individuales, playlists completas y conversión a MP3.

---

## Requisitos

| Requisito | Cómo obtenerlo |
|-----------|---------------|
| **Windows 10 / 11** | — |
| **Python 3.8 o superior** | [python.org/downloads](https://www.python.org/downloads/) — marcar ✅ *Add Python to PATH* |

> **ffmpeg ya no es necesario.** Sin él, el audio se guarda en M4A (calidad original) y el video en MP4 de hasta 720p. Si `imageio-ffmpeg` está instalado (lo hace `dependencias.bat`) o ffmpeg está en el PATH, se activa MP3 real y video hasta 1080p+.

---

## Instalación y compilación

El proceso se divide en dos pasos con scripts separados:

### Paso 1 — Instalar dependencias
```
Doble clic en  dependencias.bat
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

## Organización del código

`main.py` inicia la aplicación. El resto está separado por responsabilidad dentro de `yt_downloader/`:

- `config.py` contiene rutas y valores predeterminados.
- `runtime.py` localiza ffmpeg, runtimes JavaScript y archivos auxiliares.
- `services.py` reúne la lógica de yt-dlp, autenticación y actualizaciones.
- `errors.py` normaliza y clasifica errores.
- `workers.py` ejecuta análisis, descargas y actualizaciones en hilos.
- `widgets.py` define las filas de playlist y las tarjetas de descarga.
- `view.py` construye las secciones visuales y representa resultados.
- `window.py` conserva el estado y coordina eventos y descargas.
- `theme.py` mantiene los colores compartidos.

El comando de compilación sigue siendo `compilar.bat`; el `.spec` incluye los módulos del paquete automáticamente.

---

### Paso 3 (opcional) — Crear el instalador
Instala [Inno Setup 6](https://jrsoftware.org/isdl.php) (`winget install JRSoftware.InnoSetup`) y vuelve a ejecutar `compilar.bat`.
Además del .exe generará `instalador\YT_Downloader_Setup.exe`: un solo archivo que puedes copiar a cualquier PC con Windows 10/11.
No requiere Python, ffmpeg ni permisos de administrador. Crea acceso directo en el menú inicio/escritorio y desinstalador.

---

## Uso

1. Abre `dist\YT_Downloader.exe` (puedes moverlo donde quieras)
2. Pega la URL de un video o playlist de YouTube
3. Haz clic en **Analizar**
4. Elige formato (MP4, MP3, M4A u Opus) y calidad de video
5. Haz clic en **↓ Descargar**

Las descargas se guardan en:
```
C:\Users\TU_USUARIO\Descargas_YouTube\
```

### Pausar, reanudar y reintentar

Cada descarga tiene su propio botón:

- **⏸ Pausar** detiene la descarga (también si todavía está en cola). Lo descargado se conserva.
- **▶ Reanudar** continúa desde donde quedó, no desde cero.
- **↻ Reintentar** aparece si hubo un error.

Si cierras la app con descargas en curso, se pausan solas y puedes volver a bajarlas después (retoma el archivo parcial).

### Mismo video en varios formatos

Puedes descargar un video como MP4 y después el mismo video como MP3, M4A u Opus. M4A y Opus se descargan sin conversión y no necesitan ffmpeg. Opus se guarda en su contenedor WebM. MP3 requiere ffmpeg; si no está disponible, la app conserva el audio original sin conversión. Cada tarjeta muestra el formato descargado. Solo se evita duplicar una descarga idéntica que siga activa, en cola o pausada.

### Botón ⟳ Actualizar

Actualiza las dependencias del programa (yt-dlp y ffmpeg) y es lo primero que conviene probar si YouTube empieza a fallar:

- **Con `py main.py`:** usa pip para actualizar `yt-dlp` e `imageio-ffmpeg`.
- **Con el .exe instalado:** descarga el yt-dlp más reciente desde PyPI (verifica su SHA-256) y lo guarda en `%LOCALAPPDATA%\YT_Downloader`. No hace falta reinstalar ni recompilar. Si más adelante instalas un .exe nuevo, esa copia se descarta y se usa la que trae el .exe.

Al terminar, la app ofrece reiniciarse para aplicar la actualización.

### Descargar playlists

Cuando pegas una URL de playlist, la app muestra hasta 200 videos con checkboxes e indica si hay más elementos. Puedes:
- Seleccionar / deseleccionar videos individualmente
- Usar los botones **Todos**, **Ninguno** o **Invertir**
- Controlar cuántos videos se descargan a la vez (1–5) para no saturar la conexión

---

## Opciones de descarga

| Opción | Descripción |
|--------|-------------|
| **MP4 — Video** | Video con audio. Calidades: Mejor, 1080p, 720p, 480p |
| **MP3 — Audio** | MP3 con el bitrate elegido si hay ffmpeg; si no, audio original sin conversión |
| **Calidad MP3** | Seleccionable a 128, 192 o 320 kbps; requiere ffmpeg |
| **M4A — Audio original** | Descarga directa, sin ffmpeg ni recodificación |
| **Opus (WebM)** | Descarga directa de audio Opus en contenedor WebM, sin ffmpeg |
| **Carpeta de destino** | Elige dónde guardar las descargas |
| **Límite de velocidad** | Sin límite o un máximo en KB/s por descarga |
| **Omitir ffmpeg** | Descarga MP4 como archivo único y guarda MP3 como audio original M4A; M4A y Opus siempre funcionan sin ffmpeg |
| **Pausa / Reanudar** | Botón en cada descarga; retoma desde donde quedó |
| **Descargas a la vez** | Cuántos videos de la playlist se descargan en paralelo (1–5, default: 2) |

La carpeta, formato, calidades, velocidad máxima y cantidad de descargas simultáneas se guardan para la próxima sesión. La calidad MP3 solo afecta a MP3 convertido; M4A y Opus conservan el audio original.

> **Tip de rendimiento:** Si la computadora se pone lenta durante descargas de playlist, reduce "Descargas a la vez" a 1.

### Compilación ligera o completa

Al compilar, elige **L** para no incluir ffmpeg y reducir el tamaño del ejecutable; MP4/M4A/Opus siguen disponibles y MP3 requiere ffmpeg instalado por separado. Elige **C** para incluir ffmpeg y habilitar conversión a MP3. El tamaño final depende de las versiones de las dependencias.

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

**"[WinError 5] Acceso denegado" al terminar una descarga o conversión**
→ Otro programa (casi siempre el antivirus de Windows escaneando el archivo recién creado, o OneDrive) lo tiene abierto justo cuando la app intenta renombrarlo. La app ya espera y reintenta sola hasta 4 veces. Si aun así se repite, pulsa **Reintentar** (lo ya descargado se conserva) o agrega la carpeta de descargas como exclusión en *Seguridad de Windows → Protección contra virus → Exclusiones*.

**"HTTP Error 416: Requested range not satisfiable"**
→ El archivo parcial guardado ya no coincide con el video. La app ahora vuelve a intentar esa descarga desde cero; si falla de nuevo, pulsa **Reintentar**.

**"Failed to remove temporary directory _MEI..." al cerrar el .exe**
→ Una versión anterior del ejecutable dejó un proceso hijo usando archivos temporales. Vuelve a compilar e instalar el ejecutable actual; ahora incluye `psutil` para terminar esos procesos al cerrar.

**"ModuleNotFoundError: No module named 'PyQt6'" al ejecutar `main.py`**
→ Estás usando un Python distinto al que instaló las dependencias (por ejemplo, el botón ▷ de VS Code usa otro intérprete). Ejecuta con el mismo Python que usó `dependencias.bat`: `python main.py` (o `py -3.12 main.py`), o elige el intérprete correcto en VS Code (*Ctrl+Shift+P → Python: Select Interpreter*).

**"ERROR: This video is not available" (pero el video sí existe)**
→ Desde noviembre de 2025 YouTube exige que yt-dlp resuelva un desafío en JavaScript. Sin un motor JS (Deno) más el paquete `yt-dlp-ejs`, yt-dlp usa un solo cliente de YouTube y muchos videos fallan con ese mensaje engañoso. La app ya incluye `yt-dlp-ejs` y, si falta el motor JS, ofrece instalar Deno al abrirla (o con el botón **⟳ Actualizar**). Si el video tampoco abre en tu navegador, entonces sí es privado, fue eliminado o está bloqueado en tu país.

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

---

## Crear un instalador (Setup.exe)

Para instalar la app en cualquier PC con Windows (sin Python ni nada):

1. Instala Inno Setup una sola vez: `winget install JRSoftware.InnoSetup`
2. Doble clic en `compilar.bat` (compila el .exe y crea el instalador en el mismo paso)
3. Obtendrás `instalador\YT_Downloader_Setup.exe`. Ese único archivo es el que compartes e instalas en otras PCs.

El instalador crea acceso directo en el menú Inicio (y opcionalmente en el escritorio) y un desinstalador. **No** incluye tu `cookies.txt`.
