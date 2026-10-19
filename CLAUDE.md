# Encarta

Web local de consulta para preparar el podcast: buscar por artista, álbum, canción, sello,
género o año y ver todo lo que sabemos de ello, con aspecto de Wikipedia en modo noche.
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
entra solo; para que salga con título completo, autor y enlace, añadirlo a `BOOKS` en `build.py`.

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

## Web

`serve.py` (API JSON + estáticos de `web/`): `/api/search`, `/api/entity/<id>`, `/api/year/<año>`,
`/api/list/<id>`, `/api/random`, `/api/stats`, `/api/img/<id>` y `/api/yt?q=`. La ficha de un género suma la de sus alias.

Lo que falta se busca fuera al pedirlo y se guarda en `cache.db` (escribible, aparte de `encarta.db` para
sobrevivir a las reconstrucciones; lo no encontrado se reintenta al mes): fotos y portadas en la API pública
de Deezer (`/api/img`) y vídeos con `yt-dlp ytsearch1:` (`/api/yt`, ~1 s la primera vez).

**Reproductor flotante** (`#player` en `index.html`, fuera de `#main` para que siga sonando al navegar): cada
botón `button.play` lleva `data-yt` (id conocido) o `data-q` (se busca al pulsar); pulsar otro cambia el vídeo.
Las notas de podcast llevan «▶ Episodio» con el vídeo del episodio (las URL de ensayos son de YouTube).
Usa `youtube-nocookie.com/embed`, como Music_Books: funciona servida por HTTP; en Chromium sin interfaz
YouTube responde «vídeo no disponible», así que la reproducción solo se comprueba en un navegador normal.
Cada sección (h2) se pliega pulsando su título; las plegadas se recuerdan por título en `localStorage`
(`encarta.closed`). Las tablas de obras llevan la columna «Fuentes» (`with_sources` en `serve.py`): libros,
podcasts (con nº de notas) y listas (con puesto) que citan cada disco o canción.
El podcast y el episodio de cada nota se resuelven en `build.py` por el id de YouTube de su URL, buscándolo
en los nombres de fichero `… [id].md` de `resumenes/` y `transcripts/` de ensayos (`load_episodes`).
`web/app.js` es una SPA sin dependencias con rutas por hash (`#/e/<id>`, `#/year/1979`, `#/lista/<id>`,
`#/buscar?q=&t=`, `#/azar`). Las notas al pie numeradas enlazan al episodio. Paleta y fuentes en el `:root` de `web/style.css`.
Atajo: `/` enfoca el buscador.

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
(`link()` y `listLink()` consultan `STATIC.ids` / `STATIC.lists`). Rutas relativas: funciona bajo
`usuario.github.io/repo/`. `publish_gh_pages.sh <repo>` hace push forzado de una rama `gh-pages` huérfana.

## Añadir datos nuevos

Encarta no se edita: se reconstruye leyendo las fuentes. Podcasts nuevos → pipeline de ensayos hasta
regenerar `music_facts.db` (un podcast nuevo sale con el nombre de su carpeta; nombre bonito en `PODCASTS`
de `build.py`, abreviatura para las etiquetas en `SHORT_PODCAST` de `web/app.js`). Libros nuevos → carpeta
de Music_Books con su `index.html` (título, autor y URL en `BOOKS`). Listas → sus scripts en rym_lastfm.
Después `./main.sh deploy` (y `./main.sh static` + `publish_gh_pages.sh` si se publica en GitHub Pages).

Cómo actualizar cada fuente y Encarta: `instrucciones.md`. Los comandos de atuin están en `atuin/*.sh` (etiqueta `arco`);
`./atuin/instalar.sh` los da de alta o los actualiza en atuin.
