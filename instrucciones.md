# Actualizar los proyectos musicales

Todo se hace en el portátil. Cada fuente se actualiza por su lado y, al final, se reconstruye Encarta:

```bash
atuin scripts run <fuente>     # ensayos_podcast, ensayos, libros, must_hear_*, rym_generos
atuin scripts run encarta      # siempre al terminar
```

| Comando | Qué hace | Pregunta |
|---|---|---|
| `ensayos_podcast` | descarga, transcribe (Whisper) y resume con Claude | URL, carpeta, nombre, máx. episodios |
| `ensayos` | resume con Claude lo transcrito y crea `music_facts.db` | — |
| `libros` | regenera un libro de Music_Books | carpeta del libro |
| `must_hear_nueva` | añade una serie de MusicBrainz como colección | URL de la serie, nombre |
| `must_hear_singles` | actualiza las listas de singles | — |
| `rym_pendientes` | cuántos charts de género de RYM faltan | — |
| `rym_generos` | scrapea los charts de un género padre | género padre |
| `encarta` | reconstruye Encarta y la sube a pepecono | — |
| `encarta_gh` | publica la versión reducida en GitHub Pages | repo |
| `encarta_fechas` | busca el año de lo que no tiene fecha y sube Encarta | opciones (vacío o `--todo`) |

Los comandos están en `encarta/atuin/*.sh`. Si se cambian: `./atuin/instalar.sh`.

## Ensayos (podcasts) — `~/gits/pollo/ensayos-musicales`

1. **Podcast, canal o lista nuevos**: `atuin scripts run ensayos_podcast` con la URL (vídeo, lista o canal de
   YouTube, o feed RSS) y una carpeta corta (`central_sonora`). Descarga solo lo que falta (`mp3_input/<carpeta>/<carpeta>.log`),
   transcribe con Whisper y extrae los datos con Claude (`claude -p`, mismo prompt que Gemini) en `resumenes/`.
   Se puede cortar y relanzar. Necesita Whisper en el venv: `uv pip install -p ~/.local/share/venvs/ensayos-musicales openai-whisper`.
2. `atuin scripts run ensayos`: extrae con Claude lo que quede sin resumir en `transcripts/`, lo incorpora y crea
   `music_facts.db`. Si se llega al límite de uso de Claude, se para: relanzar más tarde. Con Gemini, como antes:
   `RESUMEN=gemini ./main.sh` en ensayos.
3. Revisar los artistas nuevos: `/revisar-lotes` en Claude Code dentro del proyecto.
4. Para que el podcast salga con buen nombre en Encarta: añadirlo a `PODCASTS` en `encarta/build.py`
   (y una abreviatura en `SHORT_PODCAST` de `encarta/web/app.js` si es largo).

## Libros — `~/gits/pollo/Music_Books`

- **Libro nuevo**: sesión de Claude Code en `Music_Books` siguiendo su `CLAUDE.md` («Cómo hacer la web de
  un libro nuevo»), con su tarjeta en la portada (`index.html`): de ella toma Encarta el título, el autor y la
  ruta en GitHub Pages. Después, `atuin scripts run encarta` (no hace falta tocar `encarta/build.py`).
- **Regenerar uno** tras cambiar sus datos: `atuin scripts run libros` (p. ej. `Postpunk`). Revisar los
  `DUDOSO` de YouTube (`tools/yt-ok.txt`) y publicar con `git push` en la carpeta del libro.

## Colecciones must hear — `~/gits/pollo/rym_lastfm`

- **Serie de MusicBrainz**: `atuin scripts run must_hear_nueva`.
- **Otras fuentes**, con `~/Scripts/python_venv/bin/python html_must_hear.py`:
  `--aoty-decade 2020s`, `--sputnik-years 2025`, `--scaruffi-decades --decade 10`,
  `--rym-list <url>`, `--rym-chart <url>` (añadir `--force-scrape` para rehacer una que ya existe).
- **Singles**: `atuin scripts run must_hear_singles` (solo descarga las listas que faltan o están viejas).

## Charts de RYM por género

1. `atuin scripts run rym_pendientes` → lista de géneros padre con charts por hacer
   (19-10-2026: faltan 632 de 5.915; 466 de *regional-music* y 124 de *classical-music*).
2. `atuin scripts run rym_generos` con uno de esos géneros padre. Se salta los que ya están, así que si se
   corta se puede relanzar. Abre un navegador visible para pasar Cloudflare.
3. Si RYM añade géneros nuevos: `html_must_hear.py --rym-genres-fetch` para actualizar el árbol.

## Encarta — `~/gits/pollo/encarta`

- `atuin scripts run encarta`: reconstruye `encarta.db` (~20 s) y la sube a pepecono
  (http://192.168.1.133:8777/, servicio `encarta` de REPEAT_ONE). Las fotos y vídeos ya encontrados se conservan.
- En local: `./main.sh` (http://127.0.0.1:8765/).
- GitHub Pages: `atuin scripts run encarta_gh` (pide el repo, p. ej. `git@github.com:volteret4/encarta.git`).
- Los números de las fichas son estables: los enlaces guardados siguen valiendo después de añadir datos.
- Años que faltan (canciones citadas en podcasts sin año): `atuin scripts run encarta_fechas` los busca en
  MusicBrainz y Discogs (~3 s cada una, se puede cortar y relanzar) y sube Encarta. Conviene tras añadir podcasts.

## Grapa (artículos) — `~/gits/pollo/Music_articles`

- Buscar artículos nuevos: `./main.sh fetch` (horas; se puede cortar y relanzar, sigue donde iba).
  Más artistas: `./main.sh fetch --min-weight 10`.
- Publicar: `./main.sh gh && ./publish_gh_pages.sh git@github.com:volteret4/grapa.git`.
  Encarta la enlaza sola desde sus fichas en cuanto está publicada.
