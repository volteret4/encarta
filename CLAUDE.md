# Encarta

Web local de consulta para preparar el podcast: buscar por artista, álbum, canción, sello,
género o año y ver todo lo que sabemos de ello, con aspecto de wiki: claro y limpio como PsychonautWiki, con modo noche (☾).
Interfaz y textos en español.

## Uso

```bash
./main.sh            # construye encarta.db (~20 s) y sirve en http://127.0.0.1:8765/
./main.sh build      # solo reconstruir tras actualizar alguna fuente
./main.sh serve      # solo servir
```

```bash
./main.sh deploy     # reconstruir y subir a pepecono (en vivo)
./main.sh static     # versión reducida para GitHub Pages en site/ (MIN=10 por defecto)
```

Python siempre con `python3 -I`, solo biblioteca estándar. `build.py` necesita `node` para leer los libros.

## Fuentes (solo lectura; rutas en `PATHS` de `build.py`, sobreescribibles por entorno)

| Fuente | Fichero | Qué aporta |
|---|---|---|
| ensayos-musicales | `db/music_facts.db` | notas de podcast (curiosidades, discos, canciones) por artista, sello y género; miembros, premios, charts y listas; referencias cruzadas |
| ensayos-musicales | `db/charts.db` | charts de singles (Billboard, UK, España…) y listas de discos (Scaruffi, 1001, Rolling Stone) |
| rym_lastfm | `db/must_hear_rym_new.db` | colecciones must hear (2.400 listas, 175.000 discos): portada, puntuaciones, sellos, géneros, bio |
| rym_lastfm | `db/must_hear_singles.db` | listas de singles (nº 1, year-end, Grammy, Los 40…) con portada y vídeo |
| Music_Books | `music.db` | fotos de artista y portadas (Last.fm, Deezer, Wikimedia) ya descargadas |
| Music_Books | `*/index.html` + `data/*.js` | escenas de cada libro, discos citados (★ esenciales), citas, pasajes que nombran a cada artista |

`build/dump_books.js` carga cada web de Music_Books en un sandbox de node (con un `window` falso, en el
orden de los `<script>` de su `index.html`) y vuelca su espacio de nombres a JSON. Un libro nuevo
entra solo: título, autor y enlace salen de su tarjeta en la portada de Music_Books (`book_cards`: `<h2>`, «autor · …»
de `p.by` y `data-pages`). `BOOKS` en `build.py` solo hace falta para cambiarlos (p. ej. el título completo).

## Modelo de `encarta.db` (generada, no se edita)

- `entity`: artista, álbum, canción, `work` (disco o canción citados en un libro sin saber cuál), sello, género.
  Se identifican por tipo + clave normalizada (`norm`, `artist_norm` sin «the», `label_norm` sin «Records»,
  `genre_norm` sin «music»); así se cruzan las fuentes. Las obras usan `artista|título`.
  `info` guarda en JSON los datos de ficha (primera fuente que los trae gana). `weight` ordena búsquedas.
  El `id` es estable entre reconstrucciones: hash de `tipo|clave` (blake2b, 48 bits; `IdSpace` resuelve
  colisiones), igual que el de las listas (`origen|slug` o nombre). Añadir datos no cambia el número de lo que
  ya existía, así que `#/e/<id>` y `#/lista/<id>` guardados siguen valiendo. Cambiar las reglas de
  normalización (`norm`, `label_norm`…) o el tipo de una obra (un `work` que pasa a `album`) sí cambia su id.
- `fact`: textos con fuente (`podcast`, `curiosity`, `award`, `chart`, `list`, `concert`, `xref`).
- `rel`: `by` (artista→obra), `label`, `genre`, `member`, `scene` (sello→escena), `aka` (alias de género).
- `list` / `list_item`: listas must hear, singles y charts. Las «RYM Top — X — Género» apuntan a su género.
- `mb_*`: libros, capítulos, escenas, discos citados, citas y menciones.

Las escenas de los libros con nombre de artista (p. ej. «The Fall») o de sello van a esa ficha, no a géneros.
charts.db trae algunos charts con columnas desplazadas (UK Vinyl, NME): `load_charts` los descarta.

Años: `split_title` saca el año de cualquier paréntesis del título de ensayos («Money for Nothing (1985) (with
Dire Straits)») y quita las notas de los resúmenes («(LP)», «(N/A)», «(Year unknown)», «(with …)»), no «(Remix)» ni
«(Live)». Lo que ninguna fuente fecha lo busca `fechas.py` (aparte, con red: base de datos de music-fuzzy,
MusicBrainz y Discogs con el tracklist comprobado; token `DISCOGS_TOKEN` o el de `music-fuzzy/db/.env`) y lo guarda en
la tabla `year` de `cache.db`; `load_found_years` lo usa al construir y deja el origen en `info.year_src`, que la
ficha enseña («según Discogs», con enlace; «dudosa» si MusicBrainz y Discogs discrepan más de 2 años).
Versiones: los resúmenes ponen el año del original («Have a Cigar (1975)» en la de Foo Fighters). `drop_covers` quita el
año de podcast de una obra anterior al artista (formación o nacimiento; si tiene más de una obra fechada de antes, ese año
es de un homónimo y no se usa) y `fechas.py` busca el de la versión; los años de listas y libros no se tocan.

## Web

`serve.py` (API JSON + estáticos de `web/`): `/api/search`, `/api/entity/<id>`, `/api/year/<año>`,
`/api/list/<id>`, `/api/random`, `/api/stats`, `/api/img/<id>` y `/api/yt?q=[&bad=]`. La ficha de un género suma la de sus alias.

Lo que falta se busca fuera al pedirlo y se guarda en `cache.db` (escribible, aparte de `encarta.db` para
sobrevivir a las reconstrucciones; lo no encontrado se reintenta al mes): fotos y portadas en la API pública
de Deezer (`/api/img`) y vídeos con `yt-dlp ytsearch1:` (`/api/yt`, ~1 s la primera vez).

**Reproductor flotante** (`#player` en `index.html`, fuera de `#main` para que siga sonando al navegar): cada
botón `button.play` lleva `data-yt` (id conocido) o `data-q` (se busca al pulsar); pulsar otro cambia el vídeo.
Las notas de podcast llevan «▶ Episodio» con el vídeo del episodio (las URL de ensayos son de YouTube).
Usa la API de iframes de YouTube (`youtube-nocookie.com`). Muchos ids guardados ya no se reproducen (borrados,
bloqueados en España o con la inserción limitada) y no se puede saber de antemano: oEmbed y yt-dlp los dan por buenos.
Cuando el reproductor da error (`onError`), pide `/api/yt?q=…&bad=<id>`: el servidor apunta el id en `yt_bad` de
`cache.db` y devuelve el siguiente resultado de la búsqueda (hasta 3 intentos), guardando el cambio en `yt_swap`.
Las fichas que sirve `serve.py` ya salen con el sustituto (`yt_swaps` + `fix_yt`), y `build_static.py` lo aplica al
exportar: `main.sh static` le pasa la `cache.db` local y la de pepecono (sin sustituto, el vídeo se quita y la versión
estática abre la búsqueda de YouTube). En la versión estática, si un vídeo falla, ofrece buscarlo en YouTube.
Cada sección (h2) se pliega pulsando su título. Salen plegadas todas menos la primera (la ficha y el resumen
siempre se ven); lo que el usuario abre o pliega se recuerda por título en `localStorage` (`encarta.sec`).
Al terminar un vídeo suena el siguiente ▶ de la página (`playStep`, también con ⏭). Teclas: «n» siguiente, «p» anterior,
espacio pausa (no mientras se escribe en un campo). El tema suena también en el control multimedia del navegador
(`mediaSession`: título, artista, portada y ⏮ ⏯ ⏭ desde otra pestaña o las teclas multimedia); Firefox/Zen solo
dan ⏮ ⏭ al marco que suena, así que mientras suena el vídeo la página reproduce un silencio en bucle (`syncSilence`).
Lo escuchado se guarda por «Artista — Tema» en `localStorage` (`encarta.played`, por navegador): el ▶ lleva «✓» y el
siguiente (al terminar, ⏭ o «n») se salta lo escuchado; al terminar, si no queda nada nuevo, se para. Toda `table.wikitable`
se ordena pulsando una cabecera (`sortKey`: números como números, «Fuentes» por nº de etiquetas, vacíos al final). Las tablas de obras llevan la columna «Fuentes» (`with_sources` en `serve.py`): libros,
podcasts (con nº de notas) y listas (con puesto) que citan cada disco o canción.
El podcast y el episodio de cada nota se resuelven en `build.py` por el id de YouTube de su URL, buscándolo
en los nombres de fichero `… [id].md` de `resumenes/` y `transcripts/` de ensayos (`load_episodes`).
`web/app.js` es una SPA sin dependencias con rutas por hash (`#/e/<id>`, `#/year/1979`, `#/lista/<id>`,
`#/buscar?q=&t=`, `#/azar`). Las notas al pie numeradas enlazan al episodio. Paleta y fuentes en el `:root` de `web/style.css` (claro) y
`:root[data-theme="dark"]` (noche); el tema se guarda en `localStorage` (`encarta.theme`) y el `<head>` lo aplica antes de pintar.
Página del año: escenas y artistas que empiezan en línea de tiempo (`timeline`, ventana de −40 a +30 años), discos y canciones
por nº de referencias (libros + notas + listas, columna «Refs») y notas de podcast agrupadas por tipo y ficha (`groupedFacts`).
One-hit wonder: artista con como mucho una mención en cada categoría (libros; notas de podcast suyas y de sus obras; entradas de
sus obras en listas) y alguna en total. `build.py` los guarda en la tabla `ohw`, `serve.py` marca `ohw: true` en las respuestas
(`mark_ohw`, también en la exportación estática) y la web añade un «₁» tras el nombre.
Atajos: `/` enfoca el buscador; `n`, `p` y espacio manejan el reproductor.

Verificar en un navegador sin interfaz:
`chromium --headless=new --no-sandbox --window-size=1400,1500 --virtual-time-budget=5000 --screenshot=/ruta/x.png "http://127.0.0.1:8765/#/e/<id>"`

## Despliegues

**En vivo, pepecono** (`ssh pepecono`, 192.168.1.133): servicio `encarta` del proyecto docker compose
REPEAT_ONE (`~/contenedores/repeat-one`, perfil `encarta`, puerto **8777**; el 8765 es de bandcamp allí).
Como `techno_consejero`, no es submódulo: `services/encarta/` es copia de este directorio y
`deploy_pepecono.sh` sube con rsync el código y `encarta.db` (se construye aquí, donde están las fuentes)
y reconstruye el contenedor; `--db` sube solo la base, que el servidor recoge en caliente.
`services/encarta/data/` es el bind mount con `encarta.db` y `cache.db` (la caché de allí, distinta de la local).
Está registrado en `docker-compose.yml`, `scripts/up.sh`, `scripts/profile_ports.sh`, `index/app.py` y
`README.md` de REPEAT_ONE. No tiene `.subdomain.conf` de SWAG: solo es accesible en la red local
(publicarlo fuera sería `scripts/gen_proxy_confs.sh encarta` allí).

**GitHub Pages, versión reducida**: `build_static.py` escribe en `site/` las fichas con `weight >= 10`
(~21.000, ~300 MB), los años 1900–2026, las listas que no son «RYM Top» y `data/index.json` para buscar en
el navegador. `web/app.js` detecta `window.ENCARTA_STATIC` (lo inyecta el build) y entonces lee
`data/e|y|l/<id>.json` en vez de la API, busca en el índice, pide las fotos a Deezer por JSONP y, sin
yt-dlp, abre la búsqueda de YouTube para los temas sin vídeo. Lo no exportado sale sin enlace
(`link()` y `listLink()` consultan `STATIC.ids` / `STATIC.lists`); las «RYM Top», que no se exportan, enlazan a su página en
`volteret4.github.io/must_hear/rym_charts/<slug>/`, con los slugs de `rym_slugs` en `stats.json`). Rutas relativas: funciona bajo
`usuario.github.io/repo/`. `publish_gh_pages.sh <repo>` hace push forzado de una rama `gh-pages` huérfana.

## Añadir datos nuevos

Encarta no se edita: se reconstruye leyendo las fuentes. Podcasts nuevos → pipeline de ensayos hasta
regenerar `music_facts.db` (un podcast nuevo sale con el nombre de su carpeta; nombre bonito en `PODCASTS`
de `build.py`, abreviatura para las etiquetas en `SHORT_PODCAST` de `web/app.js`). Libros nuevos → carpeta
de Music_Books con su `index.html` y su tarjeta en la portada (de ahí salen título, autor y URL). Listas → sus scripts en rym_lastfm.
Después `./main.sh deploy` (y `./main.sh static` + `publish_gh_pages.sh` si se publica en GitHub Pages).

Cómo actualizar cada fuente y Encarta: `instrucciones.md`. Los comandos de atuin están en `atuin/*.sh` (etiqueta `arco`);
`./atuin/instalar.sh` los da de alta o los actualiza en atuin.

## Portada

Recuadros con «↻» (otros al azar) y «→» (página `#/todos/<categoría>` con la lista completa): artistas, discos,
sellos y géneros al azar (`/api/sample`, `weight >= 25` y nombre de hasta 60 caracteres; las páginas completas
usan `/api/browse`, paginadas y filtrables), libros (10 al azar), podcasts (15) y fuentes de Grapa (15, de su
`data/cabeceras.json`; la página «Artículos» las lista con artículos, notas y tipos). Bloques al azar, enlaces al árbol de
géneros y al listado de charts de RYM (publicados por rym_lastfm en volteret4.github.io/must_hear/), libros,
años, podcasts (de las carpetas de `transcripts/` de ensayos; su web o canal en `PODCAST_URLS` de `build.py`,
o la URL de su `podcast.env`) y «Artículos», que enlaza a Grapa.

## Grapa (artículos)

Grapa es el fanzine de reseñas y entrevistas de `../Music_articles`, repo aparte publicado en
https://volteret4.github.io/grapa/. `web/app.js` (`GRAPA_URL`, `loadGrapa`) pide su `data/artistas.json` en
todas las versiones (local, pepecono y estática; GitHub Pages permite pedirlo desde otro dominio) y añade la
sección «En la prensa» a las fichas de artista y disco y el enlace de la portada. Si no responde, no sale nada.
El pie lleva las cifras; en la versión estática son las de lo exportado (`build_static.py`).
