# YT Downloader 🎬

Aplicación de escritorio para Windows que descarga videos y audios de YouTube y de cientos de sitios más sin necesidad de abrir un navegador. Soporta videos individuales, playlists completas y conversión a MP3.

---

## Requisitos

| Requisito | Cómo obtenerlo |
|-----------|---------------|
| **Windows 10 / 11** | — |
| **Python 3.11 o superior** (desarrollado con 3.12) | [python.org/downloads](https://www.python.org/downloads/) — marcar ✅ *Add Python to PATH* |

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
- Instala PyQt6, yt-dlp (con curl-cffi, necesario para TikTok), PyInstaller y psutil vía pip
- Instala `imageio-ffmpeg` (opcional), que trae un ffmpeg listo para MP3 sin tocar el PATH

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

`main.py` inicia la aplicación. El resto está separado por responsabilidad dentro de `models/`:

- `config.py` contiene rutas y valores predeterminados.
- `runtime.py` localiza ffmpeg, runtimes JavaScript y archivos auxiliares.
- `services.py` reúne la lógica de yt-dlp, autenticación y actualizaciones.
- `errors.py` normaliza y clasifica errores.
- `workers.py` ejecuta análisis, revisión de duplicados, descargas y actualizaciones en hilos.
- `downloads.py` compara los títulos con nombres de archivos existentes (incluye subcarpetas), ignorando etiquetas de relleno como «Official Video».
- `appupdate.py` consulta GitHub Releases, descarga, verifica y aplica las actualizaciones de la app.
- `menus.py` construye la barra de menú y la ventana de Ajustes.
- `widgets.py` define las filas de playlist y las tarjetas de descarga.
- `view.py` construye las secciones visuales y representa resultados.
- `manager.py` es la cola de descargas: estado de cada tarea (`TaskState`), límite de descargas simultáneas, pausa, reintento y quitar, sin tocar la interfaz.
- `window.py` coordina la interfaz: crea las tarjetas y reacciona a las señales del `DownloadManager`.
- `theme.py` mantiene los colores compartidos.
- `logs.py` configura el archivo de registro y captura las excepciones no controladas.

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

### Otros sitios además de YouTube

La app usa yt-dlp, así que el campo de URL acepta enlaces de TikTok, Instagram, Facebook, X (Twitter), Vimeo y [cientos de sitios más](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md). El análisis, la vista previa, la cola y las playlists funcionan igual. Algunos sitios piden iniciar sesión: en ese caso usa un `cookies.txt` junto a la app.

**TikTok** necesita el componente `curl-cffi` (permite a yt-dlp identificarse como un navegador). Sin él, el error es `Unexpected response from webpage request`. `dependencias.bat`, `compilar.bat` y `requirements.txt` ya lo instalan, y el `.exe` lo incluye. Si ejecutas con `py main.py` y falla, instálalo con `pip install -U "yt-dlp[default,curl-cffi]"` y reinicia. Si el error persiste, la app reintenta con `cookies.txt` y con las cookies del navegador; prueba también Herramientas → Actualizar yt-dlp.

### Descargar varios enlaces a la vez

**Archivo → Descargar varios enlaces (pegar lista)…** (`Ctrl+L`) abre un cuadro donde pegas los enlaces, **uno por línea**. Debajo se muestra cuántos son válidos. Si prefieres un archivo, el botón **Cargar desde .txt…** del mismo cuadro agrega su contenido. Al pulsar **Agregar a la cola** se descargan con el formato y la calidad elegidos en ese momento.

```
# Las líneas que empiezan con # se ignoran
https://www.youtube.com/watch?v=XXXXXXXXXXX
https://www.tiktok.com/@usuario/video/123
https://www.youtube.com/playlist?list=PLxxxx
```

- Si un enlace es una playlist, se agregan sus videos.
- Se ignoran líneas vacías y enlaces repetidos.
- Se aplica la misma revisión de duplicados que en una descarga normal.
- Al terminar, un aviso lista los enlaces que no se pudieron usar y el motivo.

### Pausar, reanudar y reintentar

Cada descarga tiene su propio botón:

- **⏸ Pausar** detiene la descarga (también si todavía está en cola). Lo descargado se conserva.
- **▶ Reanudar** continúa desde donde quedó, no desde cero.
- **↻ Reintentar** aparece si hubo un error.
- **✕ Quitar de la lista** elimina la tarjeta, pero no borra archivos descargados. Si está descargando, la pausa y la quita al detenerse; el archivo parcial se conserva.

**Todas a la vez:** sobre la lista de descargas hay tres botones: **⏸ Pausar todas** (activas y en espera), **▶ Reanudar todas** (en el orden en que se agregaron, respetando el límite de descargas simultáneas) y **✕ Cancelar todas** (pide confirmación y quita de la lista todo lo que no terminó; no borra archivos).

Si cierras la app con descargas en curso o con un análisis/actualización a medias, se pausan solas y puedes volver a bajarlas después (retoma el archivo parcial).

### Evitar archivos duplicados

Antes de iniciar una descarga, la app revisa los nombres de audio o video del mismo tipo en la carpeta de destino **y en todas sus subcarpetas** (se ignoran las carpetas ocultas o de sistema, como `.git` o `$RECYCLE.BIN`). Así puedes organizar tus descargas en carpetas y no se vuelven a bajar; el aviso muestra la ruta relativa del archivo encontrado. Si ya hay un archivo del mismo tipo con ese nombre base, lo omite aunque la extensión sea distinta. Por ejemplo, `Título.mp3` no bloquea la descarga de `Título.mp4`, pero sí evita otra descarga de audio llamada `Título`. La comparación no distingue mayúsculas y **ignora etiquetas de relleno** entre paréntesis o corchetes, o al final del título: `Official Video`, `Official Audio`, `Video Oficial`, `Lyrics`, `Letra`, `Visualizer`, `HD`, `4K`... Así `Artista - Canción (Official Video)` y `Artista - Canción (Official Audio)` cuentan como la misma canción. Cualquier otra etiqueta se conserva y hace que sea otra versión: `(Remix)`, `(Live)`, `(Acoustic)`, `(feat. X)`. El artista que venga en el título también cuenta, por lo que `Artista A - Canción` y `Artista B - Canción` no se confunden. Las palabras ignoradas están en `_NOISE_WORDS` de `models/downloads.py`. La revisión se hace en segundo plano, sin congelar la ventana. También evita poner en cola dos descargas del mismo tipo que producirían el mismo nombre.

M4A y Opus se descargan sin conversión y no necesitan ffmpeg. Opus se guarda en su contenedor WebM. MP3 requiere ffmpeg; si no está disponible, la app conserva el audio original sin conversión. Cada tarjeta muestra el formato descargado.

Cada tarjeta también muestra la velocidad y el **tiempo restante** (p. ej. `2.3 MB/s · 0:45 restante`). En MP4 con video y audio por separado, el tiempo restante corresponde al archivo que se está bajando en ese momento.

### Carátula y metadatos en MP3

Con ffmpeg disponible, los MP3 se guardan con el **título**, el **artista** (el del video o, si no existe, el canal), la fecha y la **miniatura como carátula**. Se puede desactivar en **Ajustes → Incrustar carátula y metadatos en MP3**. M4A, Opus y MP4 no se modifican.

### Menú Herramientas → Actualizar yt-dlp

Actualiza las dependencias del programa (yt-dlp y ffmpeg) y es lo primero que conviene probar si YouTube empieza a fallar:

- **Con `py main.py`:** usa pip para actualizar `yt-dlp` e `imageio-ffmpeg`.
- **Con el .exe instalado:** descarga el yt-dlp más reciente desde PyPI (verifica su SHA-256) y lo guarda en `%LOCALAPPDATA%\YT_Downloader`. No hace falta reinstalar ni recompilar. Si más adelante instalas un .exe nuevo, esa copia se descarta y se usa la que trae el .exe.

Al terminar, la app ofrece reiniciarse para aplicar la actualización.

El motor JavaScript (Deno) se instala con una **versión fija** (`DENO_VERSION` en `models/config.py`) y su SHA-256 está incluido en el propio código (`DENO_SHA256`), de modo que no depende del hash que publique el servidor de descarga. Para subir de versión, cambia `DENO_VERSION` y los hashes (se publican junto a cada release de Deno, en el archivo `.sha256sum`).

### Menú Herramientas → Buscar actualización de la app

Busca en las [Releases de GitHub](https://github.com/SergioJR2/YT_Downloader/releases) la última versión publicada y, si es más nueva que la instalada, la descarga, verifica su SHA-256, cierra la app, la actualiza y la vuelve a abrir. Al iniciar el `.exe` también la busca en segundo plano (si hay una nueva, pregunta: *Actualizar ahora*, *Más tarde* u *Omitir esta versión*).

- **Solo se instala automáticamente si la release publica un SHA-256** del archivo (GitHub lo añade solo en el campo `digest` de los assets recientes, o puedes adjuntar `YT_Downloader.exe.sha256`). Sin hash, la app no instala nada por su cuenta y ofrece abrir la página de descargas.
- Si la app se instaló con el instalador, usa `YT_Downloader_Setup.exe` (instalación silenciosa).
- Si es el `.exe` suelto, reemplaza el archivo con `YT_Downloader.exe` de la release.
- Con `py main.py` solo avisa y abre la página de descargas.

**Para publicar una versión nueva (automático, con GitHub Actions):**
1. Sube `APP_VERSION` en `models/config.py` (p. ej. `"1.5.1"`) y haz commit y push.
2. Crea y sube el tag: `git tag V1.5.1` y `git push origin V1.5.1` (debe coincidir con `APP_VERSION`).
3. El workflow **Release** (`.github/workflows/release.yml`) corre las pruebas, compila `YT_Downloader.exe` (versión Completa, con ffmpeg), crea `YT_Downloader_Setup.exe`, calcula sus `.sha256` y crea la Release con los cuatro archivos.
4. Por defecto la Release queda como **borrador** (`RELEASE_AS_DRAFT` en `release.yml`): descárgala, prueba el instalador y pulsa **Publish release**. Mientras sea borrador, la app de tus usuarios no la ve como actualización. Cambia `RELEASE_AS_DRAFT` a `"false"` cuando quieras que se publique sola.

Para probar la compilación sin publicar nada: pestaña **Actions → Release → Run workflow** sobre una rama. Deja los archivos como artefacto (14 días) y permite elegir la versión Ligera. Si falla algo después de crear el tag, corrige y usa **Re-run jobs**; si la release ya existe, solo reemplaza los archivos.

**A mano (sin Actions):** ejecuta `compilar.bat` y crea la Release en GitHub adjuntando `dist\YT_Downloader.exe`, `instalador\YT_Downloader_Setup.exe` y sus `.sha256`.

### Descargar playlists

Cuando pegas una URL de playlist, la app carga hasta 1000 videos y los muestra de 200 en 200 (botón **Mostrar más**) con checkboxes; indica cuántos hay en total. Puedes:
- Ver la **miniatura de cada video** junto a su título (se cargan en segundo plano después de analizar)
- Seleccionar / deseleccionar videos individualmente
- Usar los botones **Todos** (incluye los aún no mostrados), **Ninguno** o **Invertir**
- Controlar cuántos videos se descargan a la vez (1–5) para no saturar la conexión

---

## Menús

| Menú | Contenido |
|------|-----------|
| **Archivo** | Descargar lista desde .txt, cambiar carpeta de descarga, abrir la carpeta, salir |
| **Ajustes** | Opciones de descarga: calidad MP3, descargas a la vez, límite de velocidad, carátula y metadatos, y omitir ffmpeg |
| **Herramientas** | Actualizar yt-dlp y buscar actualización de la app |
| **Ayuda** | Versiones en GitHub, reportar un problema y acerca de |

En la pantalla principal quedan la URL, el formato (MP4, MP3, M4A, Opus), la calidad de video (solo con MP4) y las descargas.

## Opciones de descarga

| Opción | Descripción |
|--------|-------------|
| **MP4 — Video** | Video con audio. Calidades: Mejor, 1080p, 720p, 480p |
| **MP3 — Audio** | MP3 con el bitrate elegido si hay ffmpeg; si no, audio original sin conversión |
| **Calidad MP3** | Seleccionable a 128, 192 o 320 kbps; requiere ffmpeg |
| **M4A — Audio original** | Descarga directa, sin ffmpeg ni recodificación |
| **Opus (WebM)** | Descarga directa de audio Opus en contenedor WebM, sin ffmpeg |
| **Incrustar carátula y metadatos** | Activado por defecto. Solo MP3 convertido con ffmpeg: guarda título, artista, fecha y miniatura dentro del archivo |
| **Carpeta de destino** | Elige dónde guardar las descargas |
| **Evitar duplicados** | Omite títulos existentes del mismo tipo: audio con audio y video con video |
| **Límite de velocidad** | Sin límite o un máximo en KB/s por descarga |
| **Omitir ffmpeg** | Descarga MP4 como archivo único y guarda MP3 como audio original M4A; M4A y Opus siempre funcionan sin ffmpeg |
| **Pausa / Reanudar** | Botón en cada descarga; retoma desde donde quedó |
| **Quitar de la lista** | Elimina la tarjeta sin borrar el archivo descargado |
| **Descargas a la vez** | Cuántos videos de la playlist se descargan en paralelo (1–5, default: 2) |
| **Cookies del navegador** | Activado por defecto (se puede desactivar en Ajustes; al volver a activarlo pide confirmación). Solo se usan cuando YouTube pide verificar que no eres un robot la app lee la sesión de Firefox, Edge, Chrome o Brave. Alternativa sin tocar el navegador: `cookies.txt` junto a la app |

La carpeta, formato, calidades, velocidad máxima y cantidad de descargas simultáneas se guardan para la próxima sesión. La calidad MP3 solo afecta a MP3 convertido; M4A y Opus conservan el audio original.

> **Tip de rendimiento:** Si la computadora se pone lenta durante descargas de playlist, reduce "Descargas a la vez" a 1.

### Compilación ligera o completa

Al compilar, elige **L** para no incluir ffmpeg y reducir el tamaño del ejecutable; MP4/M4A/Opus siguen disponibles y MP3 requiere ffmpeg instalado por separado. Elige **C** para incluir ffmpeg y habilitar conversión a MP3. El tamaño final depende de las versiones de las dependencias.

---

## Estructura del proyecto

```
YT_Downloader/
├── main.py
├── models/                      ← Interfaz, cola de descargas, servicios, workers, registro y configuración
├── tests/                       ← Pruebas (pytest)
├── YT_Downloader.spec           ← Configuración de PyInstaller
├── dependencias.bat
├── compilar.bat
├── instalador.iss
└── README.md
```

### Pruebas

```
pip install pytest
python -m pytest tests
```

Cubren la comparación de títulos y la cola de descargas (límite simultáneo, pausa, reanudar, error, quitar y cierre). No necesitan red ni abrir ventanas.

---

## Registro de errores

Los errores inesperados se guardan en `%LOCALAPPDATA%\YT_Downloader\yt_downloader.log` (rotativo, máx. ~1.5 MB). Si ocurre uno, la app lo muestra y **sigue abierta** en lugar de cerrarse. Adjunta ese archivo al reportar un problema.

---

## Solución de problemas

**"YouTube pide verificar que no eres un robot" / "Sign in to confirm you're not a bot"**
→ Coloca un `cookies.txt` exportado de tu navegador junto a la app, o activa *Ajustes → Cookies del navegador* (inicia sesión antes en YouTube con ese navegador). Las cookies son información sensible: no compartas ese archivo.

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
