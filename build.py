#!/usr/bin/env python3
"""
build.py — construye encarta.db uniendo las tres fuentes:

  * ensayos-musicales  (db/music_facts.db, db/charts.db): lo que cuentan los podcasts
  * rym_lastfm         (db/must_hear_rym_new.db, db/must_hear_singles.db): listas must hear
  * Music_Books        (data/*.js de cada web, volcados con build/dump_books.js): los libros

Modelo:
  entity  — artista, álbum, canción, obra (disco o canción sin distinguir), sello, género.
            Se identifican por tipo + clave normalizada (sin acentos, sin «the», etc.).
  fact    — un texto sobre una entidad (curiosidad, descripción, premio, chart…), con fuente.
  rel     — relación entre entidades (artista→obra, obra→sello, obra→género, banda→miembro…).
  list / list_item — colecciones must hear, singles y listas de charts.db.
  mb_*    — escenas, discos citados, citas y menciones de los libros.

Uso: python3 -I build.py   (rutas configurables con variables de entorno, ver PATHS)
"""

import hashlib
import html
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
POLLO = os.path.expanduser('~/gits/pollo')

PATHS = {
    'ensayos': os.environ.get('ENSAYOS_DB', f'{POLLO}/ensayos-musicales/db/music_facts.db'),
    'charts': os.environ.get('CHARTS_DB', f'{POLLO}/ensayos-musicales/db/charts.db'),
    'musthear': os.environ.get('MUSTHEAR_DB', f'{POLLO}/rym_lastfm/db/must_hear_rym_new.db'),
    'singles': os.environ.get('SINGLES_DB', f'{POLLO}/rym_lastfm/db/must_hear_singles.db'),
    'books': os.environ.get('MUSIC_BOOKS', f'{POLLO}/Music_Books'),
}
OUT = os.environ.get('ENCARTA_DB', os.path.join(HERE, 'encarta.db'))
# Años que fechas.py encontró en MusicBrainz/Discogs para lo que ninguna fuente fecha (tabla `year`).
CACHE = os.environ.get('ENCARTA_CACHE', os.path.join(HERE, 'cache.db'))

# Título, autor y URL publicada de cada libro: salen solos de su tarjeta en la portada de Music_Books
# (h2, «autor · …» y data-pages; ver book_cards). Aquí solo los que se quieren con el título completo.
BOOKS = {
    'Scaruffi_Historia_del_Rock': ('A History of Rock Music 1951-2000', 'Piero Scaruffi', 'scaruffi'),
    'loops-timeline': ('Loops 1 y 2. Una historia de la música electrónica', 'Javier Blánquez (ed.)', 'loops_timeline'),
    'Postpunk': ('Postpunk. Romper todo y empezar de nuevo', 'Simon Reynolds', 'Postpunk'),
    'Jazz': ('Historia del jazz', 'Ted Gioia', 'jazz'),
    'Heavy_Metal_Weinstein': ('Heavy Metal: The Music and Its Culture', 'Deena Weinstein', 'HeavyMetal'),
    '1966_Savage': ('1966: The Year the Decade Exploded', 'Jon Savage', '1966'),
    'Funk_Vincent': ('Funk: The Music, the People, and the Rhythm of the One', 'Rickey Vincent', 'Funk'),
    'ComeUp_Abrams': ('The Come Up: An Oral History of the Rise of Hip-Hop', 'Jonathan Abrams', 'ComeUp'),
    'TechnoRebels_Sicko': ('Techno Rebels: The Renegades of Electronic Funk', 'Dan Sicko', 'TechnoRebels'),
    'Flamenco_Arbelos': ('El flamenco contado con sencillez', 'Carlos Arbelos', 'Flamenco'),
    'Salsa_Rondon': ('El libro de la salsa', 'César Miguel Rondón', 'Salsa'),
    'DarkWaves_OConnor': ('Dark Waves: The Synthesizer and the Dystopian Sound of Britain', 'Neil O’Connor', 'DarkWaves'),
}
PAGES_BASE = 'https://volteret4.github.io/'

PODCASTS = {
    'ongoing_history_of_music': 'The Ongoing History of New Music',
    'a_history_of_rock_music_in_500_songs': 'A History of Rock Music in 500 Songs',
    'music_radar_clan': 'Music Radar Clan',
    'central_sonora': 'Central Sonora',
}

# Web o canal de cada podcast para la portada. Si falta, se usa la URL de su podcast.env.
PODCAST_URLS = {
    'The Ongoing History of New Music': 'https://www.youtube.com/playlist?list=PLM8bxV0E1Gse5C3n1u-mkVSTZLL5AJICG',
    'A History of Rock Music in 500 Songs': 'https://500songs.com/',
    'Music Radar Clan': 'https://www.youtube.com/channel/UCcscSHEC5tA1aypzmKvcN0A',
    'Central Sonora': 'https://www.youtube.com/channel/UCzlALrXcVwpojaHv9zji-tg',
    'For the Record - The 70s': 'https://www.ftr70.com/',
    'Hit Parade Music History and Music Trivia': 'https://slate.com/podcasts/hit-parade',
}

PODCAST_ALIASES = {'Ongoing History of New Music': 'The Ongoing History of New Music'}

YEAR_RE = re.compile(r'\b(1[6-9]\d\d|20[0-3]\d)\b')

SCHEMA = '''
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE entity (
    id     INTEGER PRIMARY KEY,
    type   TEXT NOT NULL,            -- artist | album | song | work | label | genre
    key    TEXT NOT NULL,
    name   TEXT NOT NULL,
    artist TEXT,                     -- para obras
    year   INTEGER,                  -- obras: publicación; artistas: formación
    norm   TEXT NOT NULL,            -- nombre normalizado
    search TEXT NOT NULL,            -- nombre + artista normalizados, para buscar
    weight INTEGER NOT NULL DEFAULT 0,
    info   TEXT,                     -- JSON con los datos de ficha
    UNIQUE (type, key)
);
CREATE TABLE fact (
    id        INTEGER PRIMARY KEY,
    entity_id INTEGER,
    kind      TEXT NOT NULL,
    title     TEXT,
    body      TEXT,
    source    TEXT,
    episode   TEXT,
    url       TEXT,
    year      INTEGER,
    extra     TEXT
);
CREATE TABLE rel (
    a    INTEGER NOT NULL,
    b    INTEGER NOT NULL,
    kind TEXT NOT NULL,              -- by (artista→obra), label, genre, member, scene
    src  TEXT NOT NULL,
    PRIMARY KEY (a, b, kind, src)
) WITHOUT ROWID;
CREATE TABLE list (
    id     INTEGER PRIMARY KEY,
    src    TEXT NOT NULL,            -- musthear | singles | charts
    slug   TEXT,
    name   TEXT NOT NULL,
    grp    TEXT,
    year   INTEGER,
    url    TEXT,
    total  INTEGER,
    genre  INTEGER                   -- entidad género para los «RYM Top — X — Género»
);
CREATE TABLE list_item (
    list_id   INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,
    rank      INTEGER,
    year      INTEGER,
    note      TEXT,
    PRIMARY KEY (list_id, entity_id)
) WITHOUT ROWID;
CREATE TABLE mb_book (id INTEGER PRIMARY KEY, slug TEXT, ns TEXT, title TEXT, author TEXT, url TEXT, families TEXT);
CREATE TABLE mb_chapter (book INTEGER, n INTEGER, title TEXT, label TEXT, PRIMARY KEY (book, n));
CREATE TABLE mb_scene (
    id INTEGER PRIMARY KEY, book INTEGER, sid TEXT, entity_id INTEGER, name TEXT, family TEXT,
    start INTEGER, end INTEGER, place TEXT, descr TEXT, aka TEXT, notes TEXT,
    influences TEXT, artists TEXT, labels TEXT, chapters TEXT
);
CREATE TABLE mb_track (
    id INTEGER PRIMARY KEY, book INTEGER, scene INTEGER, entity_id INTEGER, artist_id INTEGER,
    artist TEXT, title TEXT, year INTEGER, kind TEXT, ess INTEGER, chapters TEXT, yt TEXT, pages TEXT
);
CREATE TABLE mb_ref (scene INTEGER, ch INTEGER, q TEXT, para TEXT, page INTEGER, pdf INTEGER);
CREATE TABLE mb_mention (book INTEGER, entity_id INTEGER, page INTEGER, printed INTEGER, text TEXT);
CREATE TABLE mb_scene_artist (scene INTEGER, entity_id INTEGER, rating TEXT, PRIMARY KEY (scene, entity_id)) WITHOUT ROWID;
'''

INDEXES = '''
CREATE INDEX idx_entity_norm ON entity(norm);
CREATE INDEX idx_entity_type_year ON entity(type, year);
CREATE INDEX idx_entity_artist ON entity(artist);
CREATE INDEX idx_fact_entity ON fact(entity_id);
CREATE INDEX idx_fact_year ON fact(year);
CREATE INDEX idx_rel_b ON rel(b, kind);
CREATE INDEX idx_list_item_entity ON list_item(entity_id);
CREATE INDEX idx_list_genre ON list(genre);
CREATE INDEX idx_list_year ON list(year);
CREATE INDEX idx_mb_scene_entity ON mb_scene(entity_id);
CREATE INDEX idx_mb_scene_years ON mb_scene(start, end);
CREATE INDEX idx_mb_track_entity ON mb_track(entity_id);
CREATE INDEX idx_mb_track_artist ON mb_track(artist_id);
CREATE INDEX idx_mb_track_scene ON mb_track(scene);
CREATE INDEX idx_mb_track_year ON mb_track(year);
CREATE INDEX idx_mb_ref_scene ON mb_ref(scene);
CREATE INDEX idx_mb_mention_entity ON mb_mention(entity_id);
CREATE INDEX idx_mb_scene_artist_entity ON mb_scene_artist(entity_id);
'''


# ── Normalización ────────────────────────────────────────────────────────────

def norm(s):
    """Clave de comparación: minúsculas, sin acentos ni puntuación, & = and."""
    if not s:
        return ''
    s = unicodedata.normalize('NFKD', str(s))
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace('&', ' and ').replace('’', "'")
    s = re.sub(r"[^\w\s]", ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def artist_norm(s):
    s = norm(s)
    if s.startswith('the '):
        s = s[4:]
    return s


def title_norm(s):
    s = norm(s)
    return s[4:] if s.startswith('the ') else s


def label_norm(s):
    """«Factory Records (implied)» y «Factory» son el mismo sello."""
    s = norm(re.sub(r'\([^)]*\)', ' ', s or ''))
    s = re.sub(r'^the ', '', s)
    s = re.sub(r'( (records?|recordings|label|discos|disques|schallplatten|music|musik|entertainment|ltd|inc|co))+$', '', s)
    return s or norm(s)


def genre_norm(s):
    s = norm(re.sub(r'\([^)]*\)', ' ', s or ''))
    return re.sub(r' (music|musica|scene|escena)$', '', s) or s


# Notas entre paréntesis que los resúmenes de podcast añaden al título y no son parte de él.
META_PAREN = re.compile(r"(?:\d{4}s?|mid-\d{4}s|early|late|undated|unknown|n/?a|unspecified|dates? unspecified|"
                        r"lp|ep|single|album|7\W?|12\W?|(?:with|feat\.?|featuring|ft\.?) .+)", re.I)


def split_title(raw):
    """«Closer (1980) – Subtítulo» → ('Closer', 1980, 'Subtítulo'). El año sale de cualquier paréntesis
    («Money for Nothing (1985) (with Dire Straits)» → 1985) y se quitan las notas que no son del título
    («(LP)», «(N/A)», «(1990s)», «(Undated)», «(Year unknown)», «(with …)»); «(Remix)» o «(Live)» se quedan."""
    year = None

    def paren(m):
        nonlocal year
        inner = m.group(1).strip()
        y = YEAR_RE.search(inner)
        if y and len(inner) <= 30 and not re.search(r'\d{4}s', inner):
            year = year or int(y.group(1))
            return ' '
        if META_PAREN.fullmatch(inner) or re.fullmatch(r'(?:early|mid|late)[- ]\d{4}s', inner, re.I):
            return ' '
        # «(Year unknown)», «(Year Not Specified)», «(Release date unclear)»…
        return ' ' if re.search(r'\b(?:year|date)s?\b', inner, re.I) else m.group(0)

    s = re.sub(r'\s+', ' ', re.sub(r'\(([^()]*)\)', paren, raw.strip())).strip() or raw.strip()
    for sep in (' – ', ' — ', ' - '):
        if sep in s:
            t, sub = s.split(sep, 1)
            return t.strip(), year, sub.strip()
    return s, year, ''


EPISODES = {}  # id de vídeo de YouTube → (podcast, episodio), de los ficheros de ensayos


def load_episodes():
    """Los transcripts y resúmenes de ensayos se llaman «Episodio [idDeYouTube].md» dentro de la carpeta del podcast."""
    root = os.path.dirname(os.path.dirname(PATHS['ensayos']))
    for top in ('resumenes', 'transcripts'):
        base = os.path.join(root, top)
        for dirpath, _, files in os.walk(base):
            rel = os.path.relpath(dirpath, base).split(os.sep)[0]
            if rel in ('.', 'summarized'):
                continue
            for f in files:
                m = re.match(r'^(.+?) \[([\w-]{11})\]\.(md|txt)$', f)
                if m and m.group(2) not in EPISODES:
                    EPISODES[m.group(2)] = (PODCASTS.get(rel, rel.replace('_', ' ')), clean_episode(m.group(1)))


def podcast_list(db):
    """Los podcasts de ensayos (una carpeta en transcripts/ cada uno) con su web y sus episodios en Encarta."""
    base = os.path.join(os.path.dirname(os.path.dirname(PATHS['ensayos'])), 'transcripts')
    out = []
    for d in sorted(os.listdir(base)):
        if d == 'summarized' or not os.path.isdir(os.path.join(base, d)):
            continue
        name = PODCAST_ALIASES.get(PODCASTS.get(d, d.replace('_', ' ')), PODCASTS.get(d, d.replace('_', ' ')))
        url = PODCAST_URLS.get(name)
        env = os.path.join(base, d, 'podcast.env')
        if not url and os.path.exists(env):
            for line in open(env, encoding='utf-8'):
                k, _, v = line.strip().partition('=')
                if k.lower() in ('url', 'yt_playlist', 'rss') and v.strip().strip('"'):
                    url = v.strip().strip('"')
                    break
        eps, notes = db.execute("SELECT COUNT(DISTINCT episode), COUNT(*) FROM fact "
                                "WHERE kind IN ('podcast', 'curiosity') AND source = ?", (name,)).fetchone()
        out.append({'name': name, 'url': url, 'episodes': eps, 'notes': notes})
    return out


def clean_episode(ep):
    return ep.replace('：', ':').replace('＂', '"').replace('？', '?').strip()


def parse_source(sf):
    """source_file de ensayos → (fuente, episodio, url), con el podcast resuelto por el id del vídeo."""
    src, ep, url = _parse_source(sf)
    m = re.search(r'(?:v=|youtu\.be/)([\w-]{11})', url or '')
    if m:
        # Un mismo vídeo llega con y sin «&list=…»: una sola URL por episodio.
        url = f'https://www.youtube.com/watch?v={m.group(1)}'
    known = EPISODES.get(m.group(1)) if m else None
    if known and (src in (None, 'Podcast') or src not in PODCASTS.values() and src not in PODCAST_ALIASES and
                  not re.match(r'^(Wikidata|AOTY|Scaruffi|musicbrainz|sputnikmusic|Rolling Stone|Wikipedia)', src or '')):
        # La «fuente» era en realidad el título del episodio, o no había ninguna.
        src, ep = known[0], ep or known[1]
    elif known and not ep:
        ep = known[1]
    return PODCAST_ALIASES.get(src, src), clean_episode(ep) if ep else ep, url


def _parse_source(sf):
    if not sf:
        return None, None, None
    sf = sf.split(' ← ')[0].strip()
    m = re.match(r'^([^/|]+)/(.+?)(?: \[([\w-]{11})\])?\.md$', sf)
    if m:
        d, ep, yt = m.groups()
        if d == 'artists':
            return 'Ensayos', None, None
        return PODCASTS.get(d, d.replace('_', ' ')), ep.replace('：', ':').replace('＂', '"'), (
            f'https://www.youtube.com/watch?v={yt}' if yt else None)
    if '|' in sf:
        head, url = sf.split('|', 1)
        url = url if url.startswith('http') else None
        if ' > ' in head:
            pod, ep = head.split(' > ', 1)
            return pod.strip(), ep.replace('：', ':').strip(), url
        return head.strip(), None, url
    if sf.startswith('http'):
        return 'Podcast', None, sf
    return sf, None, None


def year_of(*vals):
    for v in vals:
        if v is None:
            continue
        m = YEAR_RE.search(str(v))
        if m:
            return int(m.group(1))
    return None


# ── Registro de entidades ────────────────────────────────────────────────────

# ── Identificadores estables ─────────────────────────────────────────────────
# Los números de ficha (#/e/<id>) y de lista (#/lista/<id>) salen de un hash de su
# tipo y su clave normalizada, no del orden de carga: añadir libros, podcasts o
# listas no cambia el número de lo que ya existía, y los enlaces guardados siguen
# llevando a la misma ficha. 48 bits: cabe de sobra en un entero de JavaScript.

class IdSpace:
    def __init__(self):
        self.owner = {}  # id → identidad que lo ocupa

    def get(self, ident):
        # Una colisión (rarísima con 48 bits) se resuelve rehaciendo el hash con un sufijo.
        for n in range(100):
            raw = ident if n == 0 else f'{ident}#{n}'
            i = int.from_bytes(hashlib.blake2b(raw.encode(), digest_size=6).digest(), 'big') or 1
            if self.owner.setdefault(i, ident) == ident:
                return i
        raise RuntimeError(f'Demasiadas colisiones de id para {ident}')


LIST_IDS = IdSpace()


def new_list(db, src, ident, **cols):
    """Inserta una lista con id estable derivado de su origen y su slug o nombre."""
    lid = LIST_IDS.get(f'{src}|{ident}')
    cols = {'id': lid, 'src': src, **cols}
    db.execute(f"INSERT INTO list ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", list(cols.values()))
    return lid


class Registry:
    def __init__(self, db):
        self.db = db
        self.ids = {}       # (type, key) → id
        self.info = {}      # id → dict
        self.years = {}     # id → year
        self.cands = {}     # id → [años de cada fuente, en orden]
        self.names = {}     # id → (name, artist)
        self.space = IdSpace()

    def key(self, type_, name, artist=None):
        if type_ in ('album', 'song', 'work'):
            return f'{artist_norm(artist)}|{title_norm(name)}'
        if type_ == 'artist':
            return artist_norm(name)
        if type_ == 'label':
            return label_norm(name)
        if type_ == 'genre':
            return genre_norm(name)
        return norm(name)

    def find(self, type_, name, artist=None):
        return self.ids.get((type_, self.key(type_, name, artist)))

    def get(self, type_, name, artist=None, year=None, info=None):
        name = re.sub(r'^[*\s]+|[*\s]+$', '', name or '')
        if not name:
            return None
        k = self.key(type_, name, artist)
        if not k or k == '|' or k.endswith('|'):
            return None
        eid = self.ids.get((type_, k))
        if eid is None:
            eid = self.space.get(f'{type_}|{k}')
            self.ids[(type_, k)] = eid
            self.names[eid] = (name, (artist or '').strip() or None)
        elif type_ == 'artist' and name.lower().startswith('the ') and not self.names[eid][0].lower().startswith('the '):
            self.names[eid] = (name, None)
        if year:
            self.cands.setdefault(eid, []).append(year)
            if not self.years.get(eid):
                self.years[eid] = year
        if info:
            cur = self.info.setdefault(eid, {})
            for f, v in info.items():
                if v not in (None, '', [], {}) and f not in cur:
                    cur[f] = v
        return eid

    def work(self, title, artist, year=None, hint=None):
        """Disco o canción citados sin saber qué son: se une al que ya exista."""
        for t in ('album', 'song', 'work'):
            eid = self.find(t, title, artist)
            if eid:
                if year:
                    self.cands.setdefault(eid, []).append(year)
                    if not self.years.get(eid):
                        self.years[eid] = year
                return eid
        return self.get(hint or 'work', title, artist, year)

    def born(self):
        """{clave de artista: año de formación o nacimiento}, solo si sus obras fechadas no lo desmienten: el año del
        artista a veces es el de otro con el mismo nombre (The Monks 1979, Ghost el sueco)."""
        works = {}
        for (t, k), eid in self.ids.items():
            if t in ('album', 'song', 'work') and self.years.get(eid):
                works.setdefault(k.split('|', 1)[0], []).append(self.years[eid])
        out = {}
        for k, ys in works.items():
            aid = self.ids.get(('artist', k))
            b = self.years.get(aid) if aid else None
            # con una sola obra de antes, puede ser la versión; con más, el año del artista está mal
            if b and len([y for y in ys if y < b - 1]) <= 1:
                out[k] = b
        return out

    def drop_covers(self):
        """Un artista no tiene obras de antes de existir: ese año es el del original (los resúmenes ponen
        «Have a Cigar (1975)» en la versión de Foo Fighters). Se queda el siguiente año que dé otra fuente,
        o ninguno y fechas.py busca el de la versión. Solo con el año de los podcasts: el de una lista o un
        libro va con su disco, y si choca es que el artista es otro con el mismo nombre (Finch, Felt…)."""
        born, n = self.born(), 0
        trusted = {e for (e,) in self.db.execute('SELECT entity_id FROM list_item UNION SELECT entity_id FROM mb_track')}
        for (t, k), eid in self.ids.items():
            b = born.get(k.split('|', 1)[0])
            if (t in ('album', 'song', 'work') and b and self.years.get(eid) and self.years[eid] < b - 1
                    and eid not in trusted):
                self.years[eid] = next((y for y in self.cands.get(eid, []) if y >= b - 1), None)
                n += 1
        self.born_years = born
        return n

    def flush(self):
        type_of = {v: k[0] for k, v in self.ids.items()}
        key_of = {v: k[1] for k, v in self.ids.items()}
        rows = []
        for eid, (name, artist) in self.names.items():
            t = type_of[eid]
            rows.append((eid, t, key_of[eid], name, artist, self.years.get(eid),
                         norm(name), f'{norm(name)} {norm(artist)}'.strip(), json.dumps(self.info[eid], ensure_ascii=False) if eid in self.info else None))
        self.db.executemany('INSERT INTO entity (id,type,key,name,artist,year,norm,search,info) VALUES (?,?,?,?,?,?,?,?,?)', rows)


class Writer:
    def __init__(self, db):
        self.db = db
        self.facts = []
        self.rels = set()

    def fact(self, eid, kind, title=None, body=None, source=None, episode=None, url=None, year=None, extra=None):
        self.facts.append((eid, kind, title, body, source, episode, url, year,
                           json.dumps(extra, ensure_ascii=False) if extra else None))

    def rel(self, a, b, kind, src):
        if a and b and a != b:
            self.rels.add((a, b, kind, src))

    def flush(self):
        self.db.executemany('INSERT INTO fact (entity_id,kind,title,body,source,episode,url,year,extra) '
                            'VALUES (?,?,?,?,?,?,?,?,?)', self.facts)
        self.db.executemany('INSERT OR IGNORE INTO rel VALUES (?,?,?,?)', self.rels)


def ro(path):
    con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


# ── Fuentes ──────────────────────────────────────────────────────────────────

def load_ensayos(reg, w):
    src = ro(PATHS['ensayos'])
    art = {}
    for r in src.execute('SELECT id, name FROM artists'):
        art[r['id']] = reg.get('artist', r['name'])
    gen = {r['id']: reg.get('genre', r['name']) for r in src.execute('SELECT id, name FROM genres')}
    lab = {r['id']: reg.get('label', r['name']) for r in src.execute('SELECT id, name FROM labels')}

    for r in src.execute('SELECT band_id, member_id FROM band_members'):
        w.rel(art.get(r[0]), art.get(r[1]), 'member', 'ensayos')
    for r in src.execute('SELECT artist_id, genre_id FROM artist_genres'):
        w.rel(art.get(r[0]), gen.get(r[1]), 'genre', 'ensayos')
    for r in src.execute('SELECT artist_id, label_id FROM artist_labels'):
        w.rel(art.get(r[0]), lab.get(r[1]), 'label', 'ensayos')
    for r in src.execute('SELECT ac.artist_id, c.name FROM artist_concerts ac JOIN concerts c ON c.id = ac.concert_id'):
        if art.get(r[0]):
            # Algunos conciertos llegan como «**Título** : descripción» desde el markdown.
            m = re.match(r'^\*\*(.+?)\*\*\s*:\s*(.*)$', r[1], re.S)
            title, body = (m.group(1).strip(), m.group(2).strip()) if m else (r[1], None)
            w.fact(art[r[0]], 'concert', title, body, year=year_of(title))

    for table, type_ in (('albums', 'album'), ('songs', 'song')):
        data = 'albums_data' if table == 'albums' else 'songs_data'
        fk = 'album_id' if table == 'albums' else 'song_id'
        for r in src.execute(f'SELECT x.id, x.name, a.name AS artist, d.description, d.source_file '
                             f'FROM {table} x JOIN artists a ON a.id = x.artist_id '
                             f'LEFT JOIN {data} d ON d.{fk} = x.id'):
            title, y, sub = split_title(r['name'])
            eid = reg.get(type_, title, r['artist'], y)
            if not eid:
                continue
            w.rel(reg.get('artist', r['artist']), eid, 'by', 'ensayos')
            if r['description']:
                s, ep, url = parse_source(r['source_file'])
                w.fact(eid, 'podcast', sub or None, r['description'], s, ep, url, y)

    ctx = {'artist': art, 'genre': gen, 'label': lab}
    titles = {}
    for r in src.execute('SELECT id, title, description, context_type, context_id, source_file FROM curiosities'):
        s, ep, url = parse_source(r['source_file'])
        eid = ctx.get(r['context_type'], {}).get(r['context_id'])
        kind = 'podcast' if eid else 'curiosity'
        w.fact(eid, kind, r['title'], r['description'], s, ep, url, year_of(r['title']),
               {'ctx': r['context_type']} if not eid else None)
        if r['context_type'] == 'artist':
            titles[(r['context_id'], r['title'])] = (r['description'], s, ep, url)

    for r in src.execute('SELECT source_artist_id, target_artist_id, item_type, item_name, source_file FROM cross_references'):
        tgt = art.get(r['target_artist_id'])
        srcname = reg.names.get(art.get(r['source_artist_id']), ('',))[0]
        if not tgt:
            continue
        body, s, ep, url = titles.get((r['source_artist_id'], r['item_name']), (None, None, None, None))
        if not s:
            s, ep, url = parse_source(r['source_file'])
        w.fact(tgt, 'xref', r['item_name'], body, s, ep, url, year_of(r['item_name']),
               {'from': srcname, 'from_id': art.get(r['source_artist_id']), 'type': r['item_type']})

    for table, kind in (('awards', 'award'), ('artist_charts', 'chart'), ('artist_lists', 'list')):
        for r in src.execute(f'SELECT artist_id, title, description, source_file FROM {table}'):
            if not art.get(r['artist_id']):
                continue
            s, ep, url = parse_source(r['source_file'])
            w.fact(art[r['artist_id']], kind, r['title'], r['description'], s, ep, url, year_of(r['title'], r['description']))
    src.close()


def load_charts(reg, w, db):
    src = ro(PATHS['charts'])
    lists = {}
    for r in src.execute('SELECT chart, MIN(year), MAX(year), COUNT(*) FROM chart_entries GROUP BY chart'):
        lists[('chart', r[0])] = new_list(db, 'charts', f'chart|{r[0]}', name=r[0], grp='chart', total=r[3])
    items = {}
    for r in src.execute('SELECT artista, titulo, chart, year, position, semanas FROM chart_entries'):
        # Algunos charts traen las columnas desplazadas (posición en «artista», sin título): se descartan.
        if not r['titulo'] or str(r['artista']).isdigit() or str(r['titulo']).isdigit():
            continue
        eid = reg.get('album' if 'Album' in r['chart'] else 'song', r['titulo'], r['artista'], r['year'])
        if not eid:
            continue
        w.rel(reg.get('artist', r['artista']), eid, 'by', 'charts')
        note = f'{r["semanas"]} semanas' if r['semanas'] else None
        items[(lists[('chart', r['chart'])], eid)] = (r['position'], r['year'], note)
    for r in src.execute('SELECT id, name, source, total FROM lists'):
        lists[('list', r['id'])] = new_list(db, 'charts', f"list|{r['name']}", slug=str(r['id']), name=r['name'],
                                            grp=r['source'], total=r['total'])
    for r in src.execute('SELECT list_id, artist_name, album_name, year, rank, scaruffi_rating, aoty_score, '
                         'metacritic_score, sputnik_rating FROM list_entries'):
        eid = reg.get('album', r['album_name'], r['artist_name'], r['year'], info={
            'scaruffi': r['scaruffi_rating'], 'aoty': r['aoty_score'],
            'metacritic': r['metacritic_score'], 'sputnik': r['sputnik_rating']})
        if not eid:
            continue
        w.rel(reg.get('artist', r['artist_name']), eid, 'by', 'charts')
        items[(lists[('list', r['list_id'])], eid)] = (r['rank'], r['year'], None)
    db.executemany('INSERT OR IGNORE INTO list_item VALUES (?,?,?,?,?)',
                   [(l, e, *v) for (l, e), v in items.items()])
    src.close()


MH_LINKS = ['spotify_url', 'youtube_url', 'discogs_url', 'bandcamp_url', 'rateyourmusic_url', 'wikipedia_url',
            'lastfm_url', 'musicbrainz_url', 'allmusic_url', 'website', 'setlistfm_url', 'soundcloud_url',
            'apple_url', 'deezer_url', 'genius_url', 'metacritic_url', 'aoty_url', 'sputnikmusic_url']


def links(r):
    keys = r.keys()
    return {k.replace('_url', ''): r[k] for k in MH_LINKS if k in keys and r[k]}


def jl(v):
    if not v:
        return None
    try:
        x = json.loads(v)
        return x or None
    except (ValueError, TypeError):
        return v


def load_musthear(reg, w, db):
    src = ro(PATHS['musthear'])
    artists = {}
    for r in src.execute('SELECT * FROM artists WHERE id IN (SELECT DISTINCT a.artist_id FROM albums a '
                         'JOIN collection_albums ca ON ca.album_id = a.id)'):
        info = {
            'bio': r['bio'], 'tags': jl(r['tags']), 'country': r['country'], 'origin': r['origin'],
            'begin': r['begin_date'], 'end': r['end_date'], 'kind': r['artist_type'],
            'aliases': jl(r['aliases']), 'member_of': jl(r['member_of']), 'img': r['img_url'],
            'similar': jl(r['similar_artists']), 'listeners': r['listeners'],
            'wikipedia': r['wikipedia_content'], 'disambiguation': r['disambiguation'], 'links': links(r),
        }
        artists[r['id']] = reg.get('artist', r['name'], year=r['formed_year'] or year_of(r['begin_date']), info=info)

    genre_coll = {}
    lists = {}
    for r in src.execute('SELECT * FROM collections'):
        g = None
        parts = [p.strip() for p in r['name'].split('—')]
        if r['name'].startswith('RYM Top') and len(parts) >= 3:
            g = reg.get('genre', parts[-1])
        lists[r['id']] = new_list(db, 'musthear', r['slug'], slug=r['slug'], name=r['name'], grp=r['source_type'],
                                  url=r['source_url'], total=r['total_albums'], genre=g)
        if g:
            genre_coll[r['id']] = g

    meta = {r['album_id']: r for r in src.execute('SELECT * FROM album_metadata')}
    gnames = {r['id']: r['name'] for r in src.execute('SELECT id, name FROM genres')}
    agen = {}
    for r in src.execute('SELECT album_id, genre_id FROM album_genres'):
        agen.setdefault(r[0], []).append(gnames.get(r[1]))

    albums = {}
    for r in src.execute('SELECT al.*, ar.name AS artist FROM albums al JOIN artists ar ON ar.id = al.artist_id '
                         'WHERE al.id IN (SELECT album_id FROM collection_albums)'):
        m = meta.get(r['id'])
        info = {
            'cover': r['cover_url'], 'label': r['label'], 'kind': r['album_type'], 'tracks': r['total_tracks'],
            'media': r['media'], 'country': r['releasecountry'], 'catalog': r['catalognumber'],
            'scaruffi': r['scaruffi_rating'], 'scaruffi_note': r['scaruffi_note'], 'aoty': r['aoty_critic_score'],
            'aoty_user': r['aoty_user_score'], 'metacritic': r['metacritic_score'], 'sputnik': r['sputnik_rating'],
            'yt': r['yt_id'], 'links': links(r),
        }
        if m:
            info.update({'desc': m['desc_lfm_album'] or m['desc_mb_album'], 'wikipedia': m['wikipedia_content'],
                         'producers': jl(m['producers']), 'engineers': jl(m['engineers']), 'credits': jl(m['credits'])})
        y = r['originalyear'] or r['year']
        eid = reg.get('album', r['name'], r['artist'], y, info)
        if not eid:
            continue
        albums[r['id']] = eid
        w.rel(artists.get(r['artist_id']) or reg.get('artist', r['artist']), eid, 'by', 'musthear')
        if r['label']:
            w.rel(eid, reg.get('label', r['label']), 'label', 'musthear')
        for g in agen.get(r['id'], []) + ([r['genre']] if r['genre'] else []):
            if g:
                w.rel(eid, reg.get('genre', g), 'genre', 'musthear')

    rows = []
    for r in src.execute('SELECT collection_id, album_id, rank FROM collection_albums'):
        eid = albums.get(r[1])
        if eid:
            rows.append((lists[r[0]], eid, r[2], None, None))
            if r[0] in genre_coll:
                w.rel(eid, genre_coll[r[0]], 'genre', 'rym')
    db.executemany('INSERT OR IGNORE INTO list_item VALUES (?,?,?,?,?)', rows)
    src.close()


def load_singles(reg, w, db):
    src = ro(PATHS['singles'])
    lists = {}
    for r in src.execute('SELECT * FROM collections'):
        lists[r['id']] = new_list(db, 'singles', r['slug'], slug=r['slug'], name=r['name'], grp=r['group_slug'],
                                  year=r['year'], url=r['source_url'], total=r['total_tracks'])
    covers = {r['track_id']: r for r in src.execute('SELECT * FROM track_covers')}
    yts = {r['track_id']: r['yt_id'] for r in src.execute('SELECT track_id, yt_id FROM track_youtube')}
    tracks = {}
    for r in src.execute('SELECT t.id, t.title, t.year, a.name AS artist FROM tracks t JOIN artists a ON a.id = t.artist_id'):
        c = covers.get(r['id'])
        eid = reg.get('song', r['title'], r['artist'], r['year'], {
            'cover': c['cover'] if c else None, 'album': c['album_title'] if c else None, 'yt': yts.get(r['id'])})
        if eid:
            tracks[r['id']] = eid
            w.rel(reg.get('artist', r['artist']), eid, 'by', 'singles')
    rows = [(lists[r[0]], tracks[r[1]], r[2], r[3], (f'{r[4]} semanas' if r[4] else None) or r[5])
            for r in src.execute('SELECT collection_id, track_id, rank, year, weeks, note FROM collection_tracks')
            if r[1] in tracks]
    db.executemany('INSERT OR IGNORE INTO list_item VALUES (?,?,?,?,?)', rows)
    src.close()


def load_music_db(reg):
    """Fotos de artista y portadas que Music_Books ya trajo de Last.fm, Deezer y Wikidata."""
    path = os.path.join(PATHS['books'], 'music.db')
    if not os.path.exists(path):
        return
    src = ro(path)
    n = 0
    for r in src.execute('SELECT name, data FROM artist'):
        d = jl(r['data']) or {}
        eid = reg.find('artist', r['name'])
        if eid and (d.get('img') or d.get('bio')):
            reg.get('artist', r['name'], info={'img': d.get('img'), 'bio': d.get('bio'), 'tags': d.get('tags')})
            n += 1
    m = 0
    for r in src.execute('SELECT key, data FROM release'):
        d = jl(r['data']) or {}
        if not d.get('img') or '|' not in r['key']:
            continue
        artist, title = r['key'].split('|', 1)
        for t in ('album', 'song', 'work'):
            eid = reg.find(t, title, artist)
            if eid:
                reg.info.setdefault(eid, {}).setdefault('cover', d['img'])
                m += 1
                break
    src.close()
    log(f'  music.db: {n} artistas y {m} portadas')


def book_cards():
    """{carpeta: (título, autor, ruta en GitHub Pages)} de las tarjetas de la portada de Music_Books:
    <a class="book …" href="Carpeta/index.html" data-pages="/Ruta/"> … <h2>Título</h2> <p class="by">Autor · …</p>"""
    try:
        with open(os.path.join(PATHS['books'], 'index.html'), encoding='utf-8') as f:
            page = f.read()
    except OSError:
        return {}
    cards = {}
    for m in re.finditer(r'<a class="book[^"]*" href="([^"/]+)/index\.html"(?: data-pages="/?([^"]*?)/?")?>(.*?)</a>', page, re.S):
        title = re.search(r'<h2>(.*?)</h2>', m.group(3), re.S)
        by = re.search(r'<p class="by">(.*?)</p>', m.group(3), re.S)
        clean = lambda x: html.unescape(re.sub(r'<[^>]+>', '', x)).strip()
        cards[m.group(1)] = (clean(title.group(1)) if title else None,
                             clean(by.group(1)).split(' · ')[0] if by else '', m.group(2) or None)
    return cards


def load_books(reg, w, db):
    dump = subprocess.run(['node', os.path.join(HERE, 'build', 'dump_books.js'), PATHS['books']],
                          capture_output=True, text=True, check=True)
    if dump.stderr.strip():
        print(dump.stderr.strip(), file=sys.stderr)
    books = json.loads(dump.stdout)
    cards = book_cards()
    for b in books:
        card = cards.get(b['slug'], (None, '', None))
        title, author, pages = BOOKS.get(b['slug'], (card[0] or b['title'], card[1], card[2]))
        url = f'{PAGES_BASE}{pages}/' if pages else None
        bid = db.execute('INSERT INTO mb_book (slug, ns, title, author, url, families) VALUES (?,?,?,?,?,?)',
                         (b['slug'], b['ns'], title, author, url, json.dumps(b['families'], ensure_ascii=False))).lastrowid
        for c in b['chapters']:
            db.execute('INSERT OR REPLACE INTO mb_chapter VALUES (?,?,?,?)', (bid, c.get('n'), c.get('title'), c.get('label')))
        scaruffi = b['ns'] == 'ROCK'
        names = {g['id']: g.get('name') or g['id'] for g in b['genres']}
        yt = b['yt']
        pages_idx = b['pages']

        for g in b['genres']:
            if not g.get('name') and not g.get('tracks'):
                continue
            name = g.get('name') or g['id']
            arts = [(a['a'], a.get('r')) if isinstance(a, dict) else (a, None) for a in g.get('artists', [])]
            track_artists = {artist_norm(t['a']) for t in g.get('tracks', [])}
            # Las escenas que llevan nombre de artista (p. ej. «The Fall») van a su ficha de artista.
            if artist_norm(name) in track_artists or (len(arts) and artist_norm(name) == artist_norm(arts[0][0])):
                eid = reg.get('artist', name)
            elif reg.find('label', name):
                eid = reg.find('label', name)
            else:
                eid = reg.get('genre', name)
                for a in g.get('aka', []):
                    w.rel(reg.get('genre', a), eid, 'aka', 'books')
            notes = [{'ch': n.get('ch'), 'text': n.get('text')} for n in g.get('notes', [])]
            if g.get('note'):
                notes.append({'ch': None, 'text': g['note']})
            sid = db.execute('INSERT INTO mb_scene (book,sid,entity_id,name,family,start,end,place,descr,aka,notes,'
                             'influences,artists,labels,chapters) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                                 bid, g['id'], eid, name, g.get('family'), g.get('start'), g.get('end'),
                                 g.get('place') or None, g.get('desc'), json.dumps(g.get('aka') or [], ensure_ascii=False),
                                 json.dumps(notes, ensure_ascii=False),
                                 json.dumps([[i, names.get(i, i)] for i in g.get('influences', [])], ensure_ascii=False),
                                 json.dumps([a for a, _ in arts], ensure_ascii=False),
                                 json.dumps(g.get('labels') or [], ensure_ascii=False),
                                 json.dumps(g.get('chapters') or g.get('secs') or [], ensure_ascii=False))).lastrowid
            for a, r in arts:
                aid = reg.get('artist', a)
                if aid:
                    db.execute('INSERT OR IGNORE INTO mb_scene_artist VALUES (?,?,?)', (sid, aid, r))
            for lname in g.get('labels') or []:
                lid = reg.get('label', lname)
                w.rel(lid, eid, 'scene', 'books')
            for r in g.get('refs', []):
                ref = b['refs'].get(r.get('q'), {})
                db.execute('INSERT INTO mb_ref VALUES (?,?,?,?,?,?)',
                           (sid, r.get('ch'), r.get('q'), ref.get('para'), ref.get('page'), ref.get('pdf')))
            for t in g.get('tracks', []):
                k = f"{t['a']}|{t['t']}"
                hint = {'a': 'album', 's': 'song'}.get(t.get('k')) if scaruffi else None
                tid = reg.work(t['t'], t['a'], t.get('y'), hint)
                aid = reg.get('artist', t['a'])
                w.rel(aid, tid, 'by', 'books')
                if aid:
                    db.execute('INSERT OR IGNORE INTO mb_scene_artist VALUES (?,?,?)', (sid, aid, None))
                v = yt.get(k) or {}
                if v.get('id') and tid:
                    reg.info.setdefault(tid, {}).setdefault('yt', v['id'])
                chs = t.get('chs') or ([t['s']] if t.get('s') else [])
                pg = pages_idx.get(k) or ([[1, t['p'], None]] if t.get('p') else None)
                db.execute('INSERT INTO mb_track (book,scene,entity_id,artist_id,artist,title,year,kind,ess,chapters,yt,pages) '
                           'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                           (bid, sid, tid, aid, t['a'], t['t'], t.get('y'), t.get('k'), 1 if (t.get('ess') or t.get('best')) else 0,
                            json.dumps(chs), v.get('id'), json.dumps(pg) if pg else None))
        rows = []
        for a, ms in b['mentions'].items():
            aid = reg.find('artist', a) or reg.get('artist', a)
            for m in ms:
                rows.append((bid, aid, m[1], m[2], m[3]))
        db.executemany('INSERT INTO mb_mention VALUES (?,?,?,?,?)', rows)
        log(f'  libro {b["slug"]}: {len(b["genres"])} escenas, {len(rows)} menciones')


WEIGHTS = '''
UPDATE entity SET weight =
    (SELECT COUNT(*) FROM list_item WHERE entity_id = entity.id)
  + 3 * (SELECT COUNT(*) FROM fact WHERE entity_id = entity.id AND kind IN ('podcast','award'))
  + 5 * (SELECT COUNT(*) FROM mb_track WHERE entity_id = entity.id)
  + 5 * (SELECT COUNT(*) FROM mb_scene WHERE entity_id = entity.id)
  + (SELECT COUNT(*) FROM mb_scene_artist WHERE entity_id = entity.id)
  + (SELECT COUNT(*) FROM rel WHERE a = entity.id OR b = entity.id)
  + (SELECT COUNT(*) FROM mb_mention WHERE entity_id = entity.id) / 5;
'''


def one_hit_wonders(db):
    """Tabla `ohw`: artistas con como mucho una mención en cada categoría (libros, podcasts, listas) y alguna en total.
    Libros: discos citados, pasajes y escenas propias; podcasts: notas del artista y de sus obras; listas: entradas de
    sus obras en listas (21 discos en el mismo top de género son 21 menciones)."""
    by = dict(db.execute("SELECT b, a FROM rel WHERE kind = 'by'"))
    books, pods, lists = {}, {}, {}
    for q in ('SELECT artist_id FROM mb_track', 'SELECT entity_id FROM mb_mention', 'SELECT entity_id FROM mb_scene'):
        for (a,) in db.execute(q):
            books[a] = books.get(a, 0) + 1
    for (e,) in db.execute("SELECT entity_id FROM fact WHERE kind = 'podcast' AND entity_id IS NOT NULL"):
        a = by.get(e, e)
        pods[a] = pods.get(a, 0) + 1
    for l, e in db.execute('SELECT DISTINCT list_id, entity_id FROM list_item'):
        if e in by:
            lists[by[e]] = lists.get(by[e], 0) + 1
    ohw = []
    for (a,) in db.execute("SELECT id FROM entity WHERE type = 'artist'"):
        n = (books.get(a, 0), pods.get(a, 0), lists.get(a, 0))
        if max(n) <= 1 and sum(n) >= 1:
            ohw.append((a,))
    db.execute('CREATE TABLE ohw (id INTEGER PRIMARY KEY)')
    db.executemany('INSERT INTO ohw VALUES (?)', ohw)
    return len(ohw)


def load_found_years(reg):
    """Año de fechas.py para los discos y canciones sin año de ninguna fuente; su origen va a info.year_src."""
    if not os.path.exists(CACHE):
        return 0
    con = sqlite3.connect(f'file:{CACHE}?mode=ro', uri=True)
    try:
        rows = con.execute('SELECT type, key, year, source, url, note FROM year WHERE year IS NOT NULL').fetchall()
    except sqlite3.OperationalError:  # aún no se ha ejecutado fechas.py
        rows = []
    con.close()
    n = 0
    for typ, key, year, src, url, note in rows:
        eid = reg.ids.get((typ, key))
        b = reg.born_years.get(key.split('|', 1)[0])
        if b and year < b - 1:  # ver drop_covers
            continue
        if eid and not reg.years.get(eid):
            reg.years[eid] = year
            reg.info.setdefault(eid, {})['year_src'] = {k: v for k, v in (('src', src), ('url', url), ('note', note)) if v}
            n += 1
    return n


def main():
    for k, p in PATHS.items():
        if not os.path.exists(p):
            sys.exit(f'No existe {k}: {p}')
    tmp = OUT + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.executescript('PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;' + SCHEMA)
    reg, w = Registry(db), Writer(db)

    log('must hear (álbumes)…')
    load_musthear(reg, w, db)
    log('must hear (singles)…')
    load_singles(reg, w, db)
    log('charts y listas…')
    load_charts(reg, w, db)
    log('ensayos (podcasts)…')
    load_episodes()
    log(f'  {len(EPISODES)} episodios con vídeo')
    load_ensayos(reg, w)
    log('libros…')
    load_books(reg, w, db)
    log('fotos y portadas…')
    load_music_db(reg)
    log(f'  {reg.drop_covers()} años de antes de existir el artista quitados (versiones)')
    log(f'  {load_found_years(reg)} años de fechas.py')

    log('escribiendo entidades y hechos…')
    reg.flush()
    w.flush()
    db.executescript(INDEXES)
    log('pesos…')
    db.executescript(WEIGHTS)
    log(f'  {one_hit_wonders(db)} one-hit wonders')
    db.execute('INSERT INTO meta VALUES (?,?)', ('built', time.strftime('%Y-%m-%d %H:%M')))
    db.execute('INSERT INTO meta VALUES (?,?)', ('sources', json.dumps(PATHS)))
    db.execute('INSERT INTO meta VALUES (?,?)', ('podcasts', json.dumps(podcast_list(db), ensure_ascii=False)))
    db.commit()
    db.execute('ANALYZE')
    db.close()
    os.replace(tmp, OUT)
    con = sqlite3.connect(OUT)
    for t, n in con.execute('SELECT type, COUNT(*) FROM entity GROUP BY type'):
        log(f'  {t}: {n}')
    log(f'  hechos: {con.execute("SELECT COUNT(*) FROM fact").fetchone()[0]}')
    log(f'listo → {OUT} ({os.path.getsize(OUT) // 1_000_000} MB)')


if __name__ == '__main__':
    main()
