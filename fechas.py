#!/usr/bin/env python3
"""
fechas.py — busca el año de los discos y canciones de Encarta que ninguna fuente fecha.

Los podcasts citan muchas canciones sin año (el resumen no lo da) y algunos libros también. Este
script las busca, de la más relevante (weight) a la menos, en:
  1. la base de datos de music-fuzzy (discografías de MusicBrainz y Discogs de tus artistas; sin red)
  2. MusicBrainz: grupo de lanzamiento (discos) o grabación (canciones) con artista y título iguales
  3. Discogs: masters/ediciones del artista; en canciones, solo si el tracklist la lleva de verdad
y se queda con el año más antiguo. Lo encontrado va a la tabla `year` de cache.db, que sobrevive a las
reconstrucciones; build.py la usa para lo que ninguna fuente fecha. Lo no encontrado se reintenta a los
3 meses. Se puede cortar con Ctrl+C y relanzar: sigue donde iba.

Uso: python3 -I fechas.py [--todo] [--limit N] [--sin-red]
     (por defecto, lo citado en podcasts y libros; --todo, también lo de las listas)
Después: ./main.sh build (o deploy).
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402  (norm, artist_norm, title_norm y year_of de la construcción)

DB = os.environ.get('ENCARTA_DB', os.path.join(HERE, 'encarta.db'))
CACHE = os.environ.get('ENCARTA_CACHE', os.path.join(HERE, 'cache.db'))
MFUZZ = os.environ.get('MFUZZ_DB', os.path.expanduser('~/gits/pollo/music-fuzzy/db/sqlite/musica_local.sqlite'))
DISCOGS_ENV = os.path.expanduser('~/gits/pollo/music-fuzzy/db/.env')
UA = 'encarta-fechas/1.0 (https://github.com/volteret4/)'
RETRY = 90 * 86400
DUDOSO = 2  # años de diferencia entre MusicBrainz y Discogs para marcarla como dudosa


def loose(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    return re.sub(r'\W+', '', s.lower())


def loose_artist(s):
    """«&» = «and» y sin artículo delante: «El Aviador Dro» = «Aviador Dro»"""
    s = re.sub(r'\s*&\s*', ' and ', (s or '').lower())
    return loose(re.sub(r'^(the|el|la|los|las|le|les|die|der|das|il|i)\s+', '', s.strip()))


# Paréntesis que cambian la grabación (remezcla, directo…) frente a los que no (original mix, remaster…).
VERSION = re.compile(r'remix|rework|re-?edit|\bedit\b|\bdub\b|\bvip\b|\blive\b|en directo|acoustic|ac[uú]stic|'
                     r'instrumental|\bdemo\b|\bmix\b|version|versi[oó]n|cover', re.I)
SAME = re.compile(r'original mix|radio edit|single version|album version|remaster|\bmono\b|\bstereo\b|'
                  r'\d+\W? ?(?:inch|version)|extended|lp version', re.I)


def strip_brackets(title):
    def drop(m):
        return m.group(0) if VERSION.search(m.group(0)) and not SAME.search(m.group(0)) else ''
    return re.sub(r'\s*[(\[][^)\]]*[)\]]', drop, title or '').strip() or title


def same_title(a, b):
    """Sin paréntesis de reedición y sin artículo delante: «Crystal Ship» = «The Crystal Ship»"""
    clean = lambda x: loose(re.sub(r'^(the|a|an|el|la|los|las|le|les|die|der|das|il)\s+', '',
                                   strip_brackets(re.sub(r"[’'`]", '', x or '')).strip(), flags=re.I))
    return clean(a) == clean(b)


def lucene(s):
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r'\\\1', s)


def main_artist(a):
    return re.split(r'\s+(?:&|and|y|feat\.?|ft\.?|featuring|with|vs\.?|x)\s+|,\s*', a, flags=re.I)[0].strip()


class Web:
    """GET con JSON, una consulta por segundo y por servidor."""

    def __init__(self):
        self.last = {}
        self.down = set()  # servidores que han fallado seguido: se dejan para la próxima vez
        self.fails = {}

    def get(self, host, url, headers=None):
        if host in self.down:
            return None
        wait = 1.05 - (time.time() - self.last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            self.last[host] = time.time()
            try:
                req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json', **(headers or {})})
                with urllib.request.urlopen(req, timeout=20) as r:
                    self.fails[host] = 0
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return {}
                if e.code in (429, 503):
                    time.sleep(5 + attempt * 10)
                    continue
                break
            except (urllib.error.URLError, OSError, ValueError):
                time.sleep(2)
        self.fails[host] = self.fails.get(host, 0) + 1
        if self.fails[host] >= 5:
            print(f'⚠️  {host} no responde: sigo sin él (relanza más tarde)', file=sys.stderr)
            self.down.add(host)
        return None


class Finder:
    def __init__(self, offline=False):
        self.web = Web()
        self.offline = offline
        self.token = os.environ.get('DISCOGS_TOKEN', '')
        if not self.token and os.path.exists(DISCOGS_ENV):
            for line in open(DISCOGS_ENV):
                k, sep, v = line.strip().partition('=')
                if sep and k.strip() == 'DISCOGS_TOKEN':
                    self.token = v.strip().strip('"\'')
        if not self.token and not offline:
            print('⚠️  Sin DISCOGS_TOKEN: solo MusicBrainz', file=sys.stderr)
        self.local = self.local_index()

    @staticmethod
    def local_index():
        """{('album'|'song', clave de Encarta): (año, fuente)} de la base de datos de music-fuzzy"""
        idx = {}
        if not os.path.exists(MFUZZ):
            return idx
        src = sqlite3.connect(f'file:{MFUZZ}?mode=ro', uri=True)

        def add(kind, artist, title, y, why):
            y = build.year_of(str(y)) if y else None
            if y and artist and title:
                k = (kind, f'{build.artist_norm(artist)}|{build.title_norm(title)}')
                if k not in idx or y < idx[k][0]:
                    idx[k] = (y, why)
        try:
            for t, a, d in src.execute('SELECT title, artist_credit, first_release_date FROM mb_release_group'):
                add('album', a, t, d, 'MusicBrainz (local)')
            for t, d, rt, a in src.execute('SELECT md.title, md.first_release_date, md.release_type, a.name '
                                           'FROM musicbrainz_discography md JOIN artists a ON a.id = md.artist_id'):
                add('song' if (rt or '').lower() == 'single' else 'album', a, t, d, 'MusicBrainz (local)')
            for t, y, fmt, tl, a in src.execute("SELECT d.album_name, d.year, d.format, d.tracklist, a.name FROM discogs_discography d "
                                                "JOIN artists a ON a.id = d.artist_id WHERE d.role = 'Main'"):
                add('song' if fmt and ('Single' in fmt or '7"' in fmt) else 'album', a, t, y, 'Discogs (local)')
                for tr in json.loads(tl) if tl else []:
                    add('song', a, tr.get('title'), y, 'Discogs (local)')
        except (sqlite3.Error, ValueError) as e:
            print(f'⚠️  music-fuzzy: {e}', file=sys.stderr)
        src.close()
        return idx

    # ── MusicBrainz ──
    def mb(self, kind, artist, title):
        """(fecha, url) más antigua con artista y título iguales, '' si nada, None si no responde"""
        ent, field = ('release-group', 'releasegroup') if kind == 'album' else ('recording', 'recording')
        t = title if kind == 'album' else strip_brackets(title)
        q = urllib.parse.urlencode({'query': f'{field}:"{lucene(t)}" AND artist:"{lucene(artist)}"', 'limit': 50, 'fmt': 'json'})
        data = self.web.get('musicbrainz', f'https://musicbrainz.org/ws/2/{ent}?{q}')
        if data is None:
            return None
        best = ('', '')
        for r in data.get(f'{ent}s', []):
            credit = ''.join(c.get('name', '') + c.get('joinphrase', '') for c in r.get('artist-credit', []))
            d = r.get('first-release-date', '')
            if build.year_of(d) and same_title(r.get('title'), title) and loose_artist(credit) == loose_artist(artist):
                if not best[0] or build.year_of(d) < build.year_of(best[0]):
                    best = (d, f'https://musicbrainz.org/{ent}/{r["id"]}')
        return best

    # ── Discogs ──
    def discogs(self, kind, artist, title):
        if not self.token:
            return ('', '')
        auth = {'Authorization': f'Discogs token={self.token}'}
        t = strip_brackets(re.sub(r"[’'`]", '', title))
        found = []
        for a in dict.fromkeys([artist, main_artist(artist)]):
            for typ in ('master', 'release'):
                p = {'artist': a, 'type': typ, 'per_page': 100}
                p['release_title' if kind == 'album' else 'track'] = t
                data = self.web.get('discogs', 'https://api.discogs.com/database/search?' + urllib.parse.urlencode(p), auth)
                if data is None:
                    return None
                found = [(int(x['year']), x.get('uri', ''), x.get('resource_url', ''), x.get('title', ''))
                         for x in data.get('results', []) if str(x.get('year', '')).isdigit() and int(x['year']) > 1900
                         and 'Unofficial Release' not in x.get('format', [])]
                if kind == 'album':  # el título del resultado es «Artista - Disco»
                    found = [f for f in found if same_title(f[3].split(' - ', 1)[-1], title)]
                if found:
                    break
            if found:
                break
        for year, uri, resource, _ in sorted(found)[:4 if kind != 'album' else 1]:
            if kind != 'album':  # la búsqueda casa trozos («Home» → «Back Home»): mirar el tracklist
                data = self.web.get('discogs', resource, auth)
                if data is None:
                    return None
                if not any(same_title(tr.get('title'), title) for tr in data.get('tracklist', [])):
                    continue
            return (str(year), f'https://www.discogs.com{uri}')
        return ('', '')

    def find(self, typ, key, artist, title):
        """(año, fuente, url, nota) o None si un servicio no respondió (se reintenta la próxima vez)"""
        kinds = ('song', 'album') if typ == 'work' else (typ,)
        for k in kinds:
            if (k, key) in self.local:
                y, why = self.local[(k, key)]
                return y, why, '', ''
        if self.offline:
            return None
        got = []  # (año, fuente, url)
        for k in kinds:
            m = self.mb(k, artist, title)
            d = self.discogs(k, artist, title)
            if m is None or d is None:
                return None
            if m[0]:
                got.append((build.year_of(m[0]), 'MusicBrainz', m[1]))
            if d[0]:
                got.append((build.year_of(d[0]), 'Discogs', d[1]))
        if not got:
            return 0, '', '', ''
        y, src, url = min(got)
        ys = {s: min(g[0] for g in got if g[1] == s) for s in ('MusicBrainz', 'Discogs') if any(g[1] == s for g in got)}
        note = f'MusicBrainz {ys["MusicBrainz"]}, Discogs {ys["Discogs"]}' if len(ys) == 2 and abs(ys['MusicBrainz'] - ys['Discogs']) > DUDOSO else ''
        return y, src, url, note


def cache_db():
    con = sqlite3.connect(CACHE, timeout=10)
    con.execute('''CREATE TABLE IF NOT EXISTS year (type TEXT, key TEXT, year INTEGER, source TEXT, url TEXT,
                   note TEXT, at INTEGER, PRIMARY KEY (type, key))''')
    return con


def main():
    ap = argparse.ArgumentParser(description='Año de los discos y canciones de Encarta que ninguna fuente fecha')
    ap.add_argument('--todo', action='store_true', help='también lo que solo sale en listas (por defecto, podcasts y libros)')
    ap.add_argument('--limit', type=int, help='buscar como mucho N')
    ap.add_argument('--rehacer', action='store_true', help='volver a buscar también lo ya encontrado o no encontrado')
    ap.add_argument('--sin-red', action='store_true', help='solo la base de datos de music-fuzzy')
    a = ap.parse_args()

    db = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    where = '' if a.todo else (" AND (id IN (SELECT entity_id FROM fact WHERE kind = 'podcast') "
                               "OR id IN (SELECT entity_id FROM mb_track))")
    rows = db.execute(f"SELECT type, key, artist, name FROM entity WHERE type IN ('album', 'song', 'work') "
                      f"AND (year IS NULL OR json_extract(info, '$.year_src') IS NOT NULL) "
                      f"AND artist IS NOT NULL{where} ORDER BY weight DESC").fetchall()
    # año de formación o nacimiento: una obra de antes es otra grabación (la original de una versión).
    # Como build.Registry.born: no vale si el artista tiene más de una obra fechada de antes (es otro homónimo).
    born = dict(db.execute("SELECT key, year FROM entity WHERE type = 'artist' AND year IS NOT NULL"))
    early = {}
    for k, y in db.execute("SELECT key, year FROM entity WHERE type IN ('album', 'song', 'work') AND year IS NOT NULL"):
        a_ = k.split('|', 1)[0]
        if a_ in born and y < born[a_] - 1:
            early[a_] = early.get(a_, 0) + 1
    born = {k: y for k, y in born.items() if early.get(k, 0) <= 1}
    db.close()
    cache = cache_db()
    done = set() if a.rehacer else {(t, k) for t, k, y, at in cache.execute('SELECT type, key, year, at FROM year')
                                    if y or time.time() - at < RETRY}
    todo = [r for r in rows if (r[0], r[1]) not in done][:a.limit]
    print(f'{len(rows)} sin año, {len(todo)} por buscar' + ('' if a.sin_red else ' (~3 s cada una con red)'), flush=True)

    finder = Finder(offline=a.sin_red)
    found = doubtful = 0
    t0 = time.time()
    try:
        for i, (typ, key, artist, name) in enumerate(todo, 1):
            r = finder.find(typ, key, artist, name)
            if r is None:
                continue
            y, src, url, note = r
            b = born.get(key.split('|', 1)[0])
            if y and b and y < b - 1:
                print(f'✗ {y} < {b}  {artist} — {name}  [{src}]: de antes de existir el artista, se descarta', flush=True)
                y, src, url, note = 0, '', '', ''
            with cache:
                cache.execute('INSERT OR REPLACE INTO year VALUES (?,?,?,?,?,?,?)',
                              (typ, key, y or None, src, url, note, int(time.time())))
            found += bool(y)
            doubtful += bool(note)
            if y:
                print(f'{y}  {artist} — {name}  [{src}]' + (f'  ⚠️ dudosa: {note}' if note else ''), flush=True)
            if i % 50 == 0:
                left = (time.time() - t0) / i * (len(todo) - i)
                print(f'--- {i}/{len(todo)}, {found} con año; quedan ~{left / 60:.0f} min', flush=True)
    except KeyboardInterrupt:
        print('\nInterrumpido: lo encontrado está guardado; al relanzar sigue donde iba.')
    cache.close()
    print(f'{found} años encontrados' + (f' ({doubtful} dudosos: MusicBrainz y Discogs discrepan)' if doubtful else '')
          + '. Ahora: ./main.sh build (o deploy)')


if __name__ == '__main__':
    main()
