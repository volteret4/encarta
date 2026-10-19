#!/usr/bin/env python3
"""
serve.py — sirve la web (web/) y la API JSON sobre encarta.db.

  GET /api/search?q=…&type=all|artist|album|song|label|genre   resultados por nombre
  GET /api/entity/<id>                                          ficha completa
  GET /api/year/<año>                                           todo lo de ese año
  GET /api/list/<id>                                            una lista / chart
  GET /api/random?type=…                                        una entrada al azar
  GET /api/stats                                                cifras de portada
  GET /api/img/<id>                                             foto o portada (Deezer si falta; cacheada)
  GET /api/yt?q=…                                               vídeo de YouTube para una búsqueda (yt-dlp; cacheado)

Uso: python3 -I serve.py [--port 8765] [--host 127.0.0.1]
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import time
import unicodedata
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get('ENCARTA_DB', os.path.join(HERE, 'encarta.db'))
WEB = os.path.join(HERE, 'web')
# Caché escribible de lo que se consulta fuera (Deezer, YouTube): sobrevive a las reconstrucciones.
CACHE = os.environ.get('ENCARTA_CACHE', os.path.join(HERE, 'cache.db'))
RETRY = 30 * 86400  # se vuelve a buscar lo no encontrado al cabo de un mes

WORK_TYPES = ('album', 'song', 'work')
YT = "json_extract(e.info, '$.yt') AS yt"
# Nota de Scaruffi del disco: sus listas van ordenadas por nota, el «puesto» no significa nada.
SCARUFFI = "json_extract(e.info, '$.scaruffi') AS scaruffi"
TYPE_FILTER = {
    'artist': ('artist',), 'album': ('album', 'work'), 'song': ('song', 'work'),
    'label': ('label',), 'genre': ('genre',),
}


def norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace('&', ' and ').replace('’', "'")
    s = re.sub(r'[^\w\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def connect():
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def cache_db():
    con = sqlite3.connect(CACHE, timeout=10)
    con.executescript('''
        CREATE TABLE IF NOT EXISTS img (key TEXT PRIMARY KEY, url TEXT, at INTEGER);
        CREATE TABLE IF NOT EXISTS yt (q TEXT PRIMARY KEY, id TEXT, title TEXT, at INTEGER);''')
    return con


def rows(cur):
    return [dict(r) for r in cur]


def jl(v, default=None):
    if not v:
        return default
    try:
        return json.loads(v)
    except ValueError:
        return default


def ent(con, eid):
    r = con.execute('SELECT id, type, name, artist, year, weight, info FROM entity WHERE id = ?', (eid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d['info'] = jl(d['info'], {})
    return d


def brief(con, sql, args=()):
    """Lista corta de entidades: id, type, name, artist, year, weight."""
    return rows(con.execute(sql, args))


# ── Búsqueda ─────────────────────────────────────────────────────────────────

def search(con, q, type_='all', limit=60):
    q = norm(q)
    out = {'q': q, 'results': [], 'year': None}
    if not q:
        return out
    if re.fullmatch(r'1[6-9]\d\d|20[0-3]\d', q):
        out['year'] = int(q)
    types = TYPE_FILTER.get(type_)
    where = f"AND type IN ({','.join('?' * len(types))})" if types else ''
    args = list(types or [])
    sql = f'''
        SELECT id, type, name, artist, year, weight,
               (norm = ?) AS exact, (norm LIKE ? || '%') AS prefix
        FROM entity
        WHERE search LIKE '%' || ? || '%' {where}
        ORDER BY exact DESC, prefix DESC, weight DESC
        LIMIT ?'''
    out['results'] = rows(con.execute(sql, [q, q, q, *args, limit]))
    return out


# ── Bloques comunes de ficha ─────────────────────────────────────────────────

def facts(con, eid, kinds, limit=2000):
    ids = eid if isinstance(eid, (list, tuple)) else [eid]
    ph = ','.join('?' * len(kinds))
    res = rows(con.execute(f'SELECT kind, title, body, source, episode, url, year, extra FROM fact '
                           f"WHERE entity_id IN ({','.join('?' * len(ids))}) AND kind IN ({ph}) "
                           f'ORDER BY year IS NULL, year, title LIMIT ?',
                           (*ids, *kinds, limit)))
    # La misma nota llega a veces desde varios episodios o fuentes: una sola entrada con todas sus fuentes.
    merged = {}
    for f in res:
        f['extra'] = jl(f['extra'])
        k = (norm(f['title'] or ''), norm(f['body'] or '')[:300])
        src = {'source': f.pop('source'), 'episode': f.pop('episode'), 'url': f.pop('url')}
        if k not in merged:
            merged[k] = f
            f['srcs'] = []
        if src['source'] or src['url']:
            if src not in merged[k]['srcs']:
                merged[k]['srcs'].append(src)
    return list(merged.values())


def lists_of(con, eid):
    seen = set()
    return [r for r in rows(con.execute(f'''
        SELECT l.id, l.name, l.src, l.grp, l.year AS list_year, li.rank, li.year, li.note, l.total, {SCARUFFI}
        FROM list_item li JOIN list l ON l.id = li.list_id JOIN entity e ON e.id = li.entity_id
        WHERE li.entity_id = ? ORDER BY li.rank IS NULL, li.rank''', (eid,)))
            if not (r['name'] in seen or seen.add(r['name']))]


CHART_TITLE = re.compile(r'^[\"“](.+?)[\"”]\s*(?:\((\d{4})\))?\s*—\s*(.+)$')


def artist_charts(con, e, works):
    """
    Todas las listas y charts en que salen las obras del artista, en una tabla: las de
    must hear, singles y charts.db, más las que solo trae ensayos (sus fichas de charts y
    listas, «"Título" (año) — Lista» con «#puesto, …» en el texto) si no están ya.
    """
    ids = [w['id'] for w in works] or [0]
    ph = ','.join('?' * len(ids))
    out, seen = [], set()
    for r in con.execute(f'''
            SELECT e.id, e.type, e.name, e.year AS work_year, l.id AS list_id, l.name AS list, l.src,
                   li.rank, li.year, li.note, {YT}, {SCARUFFI}
            FROM list_item li JOIN list l ON l.id = li.list_id JOIN entity e ON e.id = li.entity_id
            WHERE li.entity_id IN ({ph})''', ids):
        k = (norm(r['name']), norm(r['list']))
        if k in seen:
            continue
        seen.add(k)
        d = dict(r)
        d['year'] = d['year'] or d.pop('work_year')
        out.append(d)
    by_title = {norm(w['name']): w for w in works}
    for f in facts(con, e['id'], ('chart', 'list')):
        m = CHART_TITLE.match(f['title'] or '')
        if not m:
            continue
        title, year, lst = m.group(1), m.group(2), m.group(3).strip()
        if (norm(title), norm(lst)) in seen:
            continue
        seen.add((norm(title), norm(lst)))
        body = f['body'] or ''
        rank = re.search(r'#(\d+)', body)
        weeks = re.search(r'(\d+)\s+semanas', body)
        w = by_title.get(norm(title), {})
        out.append({'id': w.get('id'), 'type': w.get('type'), 'name': title, 'list_id': None, 'list': lst,
                    'src': 'ensayos', 'rank': int(rank.group(1)) if rank else None,
                    'year': int(year) if year else f['year'], 'note': f'{weeks.group(1)} semanas' if weeks else None,
                    'yt': None, 'scaruffi': None,
                    'url': (f['srcs'][0]['url'] if f.get('srcs') else None)})
    out.sort(key=lambda r: (r['year'] or 9999, r['list'], r['rank'] or 0))
    return out


def book(con, bid, cache={}):
    if bid not in cache:
        r = con.execute('SELECT id, slug, title, author, url, families FROM mb_book WHERE id = ?', (bid,)).fetchone()
        d = dict(r)
        d['families'] = jl(d['families'], {})
        cache[bid] = d
    return cache[bid]


def chapter_name(con, bid, ch):
    if ch is None:
        return None
    r = con.execute('SELECT title, label FROM mb_chapter WHERE book = ? AND n = ?', (bid, ch)).fetchone()
    if r:
        return f"{r['label'] or f'Cap. {ch}'}: {r['title']}"
    return f'Sección {ch}'


def scene_entity(con, bid, sid):
    r = con.execute('SELECT s.entity_id, e.type FROM mb_scene s JOIN entity e ON e.id = s.entity_id '
                    'WHERE s.book = ? AND s.sid = ?', (bid, sid)).fetchone()
    return (r['entity_id'], r['type']) if r else (None, None)


def scene_full(con, s):
    """Escena de un libro con todo: descripción, notas, citas, artistas, discos."""
    b = book(con, s['book'])
    fam = b['families'].get(s['family'] or '', {})
    infl = []
    for sid, name in jl(s['influences'], []):
        e, t = scene_entity(con, s['book'], sid)
        infl.append({'name': name, 'id': e, 'type': t})
    notes = [{'chapter': chapter_name(con, s['book'], n.get('ch')), 'text': n.get('text')}
             for n in jl(s['notes'], [])]
    refs = rows(con.execute('SELECT ch, q, para, page, pdf FROM mb_ref WHERE scene = ?', (s['id'],)))
    for r in refs:
        r['chapter'] = chapter_name(con, s['book'], r['ch'])
    artists = brief(con, '''SELECT e.id, e.type, e.name, sa.rating FROM mb_scene_artist sa
                            JOIN entity e ON e.id = sa.entity_id WHERE sa.scene = ?
                            ORDER BY e.weight DESC''', (s['id'],))
    tracks = rows(con.execute('''SELECT t.entity_id AS id, t.artist_id, t.artist, t.title, t.year, t.kind, t.ess, t.yt,
                                        e.type FROM mb_track t LEFT JOIN entity e ON e.id = t.entity_id
                                 WHERE t.scene = ? ORDER BY t.year IS NULL, t.year''', (s['id'],)))
    labels = []
    for name in jl(s['labels'], []):
        r = con.execute("SELECT id FROM entity WHERE type = 'label' AND norm = ?", (norm(name),)).fetchone()
        labels.append({'name': name, 'id': r['id'] if r else None})
    return {
        'id': s['id'], 'name': s['name'], 'book': b, 'family': fam.get('name'), 'color': fam.get('color'),
        'start': s['start'], 'end': s['end'], 'place': s['place'], 'desc': s['descr'],
        'aka': jl(s['aka'], []), 'notes': notes, 'influences': infl, 'refs': refs,
        'artists': artists, 'tracks': tracks, 'labels': labels,
        'link': f"{b['url']}#{s['sid']}" if b['url'] else None,
    }


def scenes_of(con, eid):
    ids = eid if isinstance(eid, (list, tuple)) else [eid]
    return [scene_full(con, s) for s in con.execute(
        f"SELECT * FROM mb_scene WHERE entity_id IN ({','.join('?' * len(ids))})", ids)]


def book_tracks(con, where, args):
    res = []
    for t in con.execute(f'''SELECT t.*, s.name AS scene_name, s.entity_id AS scene_id, s.sid
                             FROM mb_track t JOIN mb_scene s ON s.id = t.scene WHERE {where}
                             ORDER BY t.year IS NULL, t.year''', args):
        b = book(con, t['book'])
        chs = jl(t['chapters'], [])
        res.append({
            'id': t['entity_id'], 'artist': t['artist'], 'artist_id': t['artist_id'], 'title': t['title'],
            'year': t['year'], 'ess': t['ess'], 'yt': t['yt'], 'kind': t['kind'],
            'book': {'id': b['id'], 'title': b['title'], 'author': b['author'], 'url': b['url']},
            'scene': t['scene_name'], 'scene_id': t['scene_id'],
            'scene_link': f"{b['url']}#{t['sid']}" if b['url'] else None,
            'chapters': [chapter_name(con, t['book'], c) if isinstance(c, int) else f'Sección {c}' for c in chs],
            'pages': jl(t['pages'], []),
        })
    return res


def mentions(con, eid, limit=300):
    res = []
    for m in con.execute('SELECT book, page, printed, text FROM mb_mention WHERE entity_id = ? '
                         'ORDER BY book, page LIMIT ?', (eid, limit)):
        b = book(con, m['book'])
        res.append({'book': b['title'], 'author': b['author'], 'page': m['printed'] or m['page'], 'text': m['text']})
    return res


def related(con, eid, kind, direction, types=None, limit=300):
    """Entidades relacionadas: direction 'out' (a = eid) o 'in' (b = eid). eid puede ser una lista."""
    ids = eid if isinstance(eid, (list, tuple)) else [eid]
    me, other = ('a', 'b') if direction == 'out' else ('b', 'a')
    tf = f"AND e.type IN ({','.join('?' * len(types))})" if types else ''
    return brief(con, f'''SELECT e.id, e.type, e.name, e.artist, e.year, e.weight, {YT},
                                 GROUP_CONCAT(DISTINCT r.src) AS src
                          FROM rel r JOIN entity e ON e.id = r.{other}
                          WHERE r.{me} IN ({','.join('?' * len(ids))}) AND r.kind = ? {tf}
                          GROUP BY e.id ORDER BY e.weight DESC LIMIT ?''', (*ids, kind, *(types or ()), limit))


def artist_of(con, name):
    from_key = norm(name)
    if from_key.startswith('the '):
        from_key = from_key[4:]
    r = con.execute("SELECT id FROM entity WHERE type = 'artist' AND key = ?", (from_key,)).fetchone()
    return r['id'] if r else None


# ── Fichas por tipo ──────────────────────────────────────────────────────────

def short_book(title):
    """«Postpunk. Romper todo…» → «Postpunk»; «Heavy Metal: The Music…» → «Heavy Metal»."""
    if title.startswith('A History of Rock Music'):
        return 'Scaruffi'
    return re.split(r'[.:]\s', title, 1)[0]


def with_sources(con, items):
    """Añade a cada obra `from`: los libros, podcasts y listas que la citan (por qué está en la tabla)."""
    ids = [w['id'] for w in items if w.get('type') in WORK_TYPES]
    if not ids:
        return items
    src = {i: {'books': [], 'podcasts': [], 'lists': [], 'n_lists': 0} for i in ids}
    for chunk in range(0, len(ids), 900):
        part = ids[chunk:chunk + 900]
        ph = ','.join('?' * len(part))
        for r in con.execute(f'''SELECT DISTINCT t.entity_id, b.title, b.author FROM mb_track t
                                 JOIN mb_book b ON b.id = t.book WHERE t.entity_id IN ({ph})''', part):
            src[r[0]]['books'].append({'name': short_book(r[1]), 'title': f'{r[1]} ({r[2]})'})
        for r in con.execute(f'''SELECT entity_id, COALESCE(source, 'Podcast'), COUNT(*) FROM fact
                                 WHERE kind = 'podcast' AND entity_id IN ({ph})
                                 GROUP BY entity_id, source ORDER BY COUNT(*) DESC''', part):
            src[r[0]]['podcasts'].append({'name': r[1], 'n': r[2]})
        # Primero las listas más selectivas; las «RYM Top» de género, al final.
        for r in con.execute(f'''SELECT li.entity_id, l.id, l.name, li.rank, {SCARUFFI}
                                 FROM list_item li JOIN list l ON l.id = li.list_id JOIN entity e ON e.id = li.entity_id
                                 WHERE li.entity_id IN ({ph})
                                 ORDER BY l.name LIKE 'RYM Top%', l.total IS NULL, l.total''', part):
            d = src[r[0]]
            if any(x['name'] == r[2] for x in d['lists']) or r[2] in d.setdefault('_seen', set()):
                continue  # la misma lista llega desde must hear y desde charts.db
            d['_seen'].add(r[2])
            d['n_lists'] += 1
            if len(d['lists']) < 4:
                d['lists'].append({'id': r[1], 'name': r[2], 'rank': r[3], 'scaruffi': r[4]})
    for w in items:
        if w['id'] in src:
            src[w['id']].pop('_seen', None)
            w['from'] = src[w['id']]
    return items


def detail_artist(con, e):
    eid = e['id']
    works = related(con, eid, 'by', 'out', WORK_TYPES, 2000)
    with_sources(con, works)
    works.sort(key=lambda w: (w['year'] or 9999, w['name']))
    ids = [w['id'] for w in works] or [0]
    ph = ','.join('?' * len(ids))
    charts = artist_charts(con, e, works)
    genres = related(con, eid, 'genre', 'out', ('genre',), 40)
    album_genres = brief(con, f'''SELECT e.id, e.type, e.name, COUNT(*) AS n FROM rel r JOIN entity e ON e.id = r.b
                                  WHERE r.kind = 'genre' AND r.a IN ({ph}) GROUP BY e.id ORDER BY n DESC LIMIT 15''', ids)
    labels = related(con, eid, 'label', 'out', ('label',), 40)
    album_labels = brief(con, f'''SELECT e.id, e.type, e.name, COUNT(*) AS n FROM rel r JOIN entity e ON e.id = r.b
                                  WHERE r.kind = 'label' AND r.a IN ({ph}) GROUP BY e.id ORDER BY n DESC LIMIT 15''', ids)
    scenes = []
    for s in con.execute('''SELECT s.id, s.book, s.name, s.entity_id, s.family, s.start, s.end, s.descr, s.sid
                            FROM mb_scene_artist sa JOIN mb_scene s ON s.id = sa.scene
                            WHERE sa.entity_id = ? AND s.entity_id != ?''', (eid, eid)):
        b = book(con, s['book'])
        fam = b['families'].get(s['family'] or '', {})
        scenes.append({'id': s['entity_id'], 'name': s['name'], 'book': b['title'], 'author': b['author'],
                       'start': s['start'], 'end': s['end'], 'desc': s['descr'], 'color': fam.get('color'),
                       'family': fam.get('name'), 'link': f"{b['url']}#{s['sid']}" if b['url'] else None})
    return {
        'works': works,
        'members': related(con, eid, 'member', 'out', ('artist',)),
        'member_of': related(con, eid, 'member', 'in', ('artist',)),
        'genres': genres, 'album_genres': album_genres,
        'labels': labels, 'album_labels': album_labels,
        'own_scenes': scenes_of(con, eid),
        'scenes': scenes,
        'book_tracks': book_tracks(con, 't.artist_id = ?', (eid,)),
        'mentions': mentions(con, eid),
        'podcast': facts(con, eid, ('podcast',)),
        'awards': facts(con, eid, ('award',)),
        'concerts': facts(con, eid, ('concert',)),
        'xref': facts(con, eid, ('xref',), 300),
        'charts': charts,
        'lists': lists_of(con, eid),
    }


def detail_work(con, e):
    eid = e['id']
    aid = artist_of(con, e['artist']) if e['artist'] else None
    artist = ent(con, aid) if aid else None
    others = []
    if aid:
        others = brief(con, '''SELECT e.id, e.type, e.name, e.year, e.weight FROM rel r JOIN entity e ON e.id = r.b
                               WHERE r.a = ? AND r.kind = 'by' AND e.id != ? GROUP BY e.id
                               ORDER BY e.weight DESC LIMIT 12''', (aid, eid))
    return {
        'artist_ref': {'id': aid, 'name': artist['name'], 'info': {'img': artist['info'].get('img')}} if artist else None,
        'labels': related(con, eid, 'label', 'out', ('label',)),
        # Primero los géneros propios del disco; los deducidos de las listas «RYM Top» al final.
        'genres': sorted(related(con, eid, 'genre', 'out', ('genre',), 30),
                         key=lambda g: (g['src'] == 'rym', -g['weight'])),
        'lists': lists_of(con, eid),
        'podcast': facts(con, eid, ('podcast',)),
        'book_tracks': book_tracks(con, 't.entity_id = ?', (eid,)),
        'others': others,
    }


def detail_label(con, e):
    eid = e['id']
    return {
        'artists': related(con, eid, 'label', 'in', ('artist',), 400),
        'works': with_sources(con, related(con, eid, 'label', 'in', WORK_TYPES, 400)),
        'scenes_rel': related(con, eid, 'scene', 'out', None, 50),
        'own_scenes': scenes_of(con, eid),
        'podcast': facts(con, eid, ('podcast',)),
    }


def detail_genre(con, e):
    eid = e['id']
    # Un género suma lo de sus alias (p. ej. «Gótico» del libro y «goth» de los podcasts).
    aka = related(con, eid, 'aka', 'out', ('genre',)) + related(con, eid, 'aka', 'in', ('genre',))
    ids = [eid] + [a['id'] for a in aka]
    rym = []
    for l in con.execute(f"SELECT id, name, total, url FROM list WHERE genre IN ({','.join('?' * len(ids))})", ids):
        items = brief(con, f'''SELECT e.id, e.type, e.name, e.artist, e.year, li.rank, {YT} FROM list_item li
                              JOIN entity e ON e.id = li.entity_id WHERE li.list_id = ?
                              ORDER BY li.rank LIMIT 50''', (l['id'],))
        rym.append({**dict(l), 'items': items})
    own = scenes_of(con, ids)
    own_ids = {s['id'] for s in own}
    return {
        'own_scenes': own,
        'similar_scenes': [s for s in similar_scenes(con, e) if s['id'] not in own_ids],
        'aka': aka,
        'rym': rym,
        'artists': related(con, ids, 'genre', 'in', ('artist',), 300),
        'works': with_sources(con, related(con, ids, 'genre', 'in', WORK_TYPES, 300)),
        'podcast': facts(con, ids, ('podcast',)),
    }


def similar_scenes(con, e):
    """Escenas de los libros cuyo nombre (o alias) contiene el del género o al revés."""
    g = norm(e['name'])
    if len(g) < 3:
        return []
    out = []
    for s in con.execute('SELECT id, book, sid, entity_id, name, aka, family, start, end, descr FROM mb_scene '
                         'WHERE entity_id != ?', (e['id'],)):
        names = [norm(s['name'])] + [norm(a) for a in jl(s['aka'], [])]
        if not any(n and (re.search(rf'\b{re.escape(g)}\b', n) or (len(n) >= max(4, 0.7 * len(g)) and re.search(rf'\b{re.escape(n)}\b', g)))
                   for n in names):
            continue
        b = book(con, s['book'])
        fam = b['families'].get(s['family'] or '', {})
        out.append({'id': s['entity_id'], 'name': s['name'], 'book': b['title'], 'author': b['author'],
                    'start': s['start'], 'end': s['end'], 'desc': s['descr'], 'color': fam.get('color'),
                    'family': fam.get('name'), 'link': f"{b['url']}#{s['sid']}" if b['url'] else None})
    return out


DETAIL = {'artist': detail_artist, 'album': detail_work, 'song': detail_work, 'work': detail_work,
          'label': detail_label, 'genre': detail_genre}


def entity_detail(con, eid):
    e = ent(con, eid)
    if not e:
        return None
    if not (e['info'].get('img') or e['info'].get('cover')):
        e['info']['img'] = cached_img(e)
    e.update(DETAIL[e['type']](con, e))
    return e


def year_detail(con, y):
    scenes = []
    for s in con.execute('''SELECT s.*, e.type AS etype FROM mb_scene s LEFT JOIN entity e ON e.id = s.entity_id
                            WHERE s.start <= ? AND COALESCE(s.end, s.start) >= ? ORDER BY s.start DESC''', (y, y)):
        b = book(con, s['book'])
        fam = b['families'].get(s['family'] or '', {})
        scenes.append({'id': s['entity_id'], 'type': s['etype'], 'name': s['name'], 'book': b['title'],
                       'start': s['start'], 'end': s['end'], 'born': s['start'] == y, 'color': fam.get('color'),
                       'desc': s['descr'], 'link': f"{b['url']}#{s['sid']}" if b['url'] else None})
    scenes.sort(key=lambda s: (not s['born'], (s['end'] or s['start']) - s['start']))
    charts = {}
    for r in con.execute(f'''SELECT l.id AS list_id, l.name AS list, l.grp, e.id, e.type, e.name, e.artist, li.rank, li.note, {YT}, {SCARUFFI}
                            FROM list_item li JOIN list l ON l.id = li.list_id JOIN entity e ON e.id = li.entity_id
                            WHERE l.src IN ('singles', 'charts') AND (li.year = ? OR (li.year IS NULL AND l.year = ?))
                            ORDER BY l.name, li.rank IS NULL, li.rank''', (y, y)):
        c = charts.setdefault(r['list_id'], {'id': r['list_id'], 'name': r['list'], 'items': []})
        if len(c['items']) < 25:
            c['items'].append(dict(r))
    return {
        'year': y,
        'albums': with_sources(con, brief(con, f'''SELECT id, type, name, artist, year, weight, {YT} FROM entity e
                                WHERE type IN ('album','work') AND year = ? ORDER BY weight DESC LIMIT 120''', (y,))),
        'songs': with_sources(con, brief(con, f'''SELECT id, type, name, artist, year, weight, {YT} FROM entity e
                               WHERE type = 'song' AND year = ? ORDER BY weight DESC LIMIT 120''', (y,))),
        'artists': brief(con, '''SELECT id, type, name, year, weight FROM entity
                                 WHERE type = 'artist' AND year = ? ORDER BY weight DESC LIMIT 80''', (y,)),
        'scenes': scenes,
        'charts': list(charts.values()),
        'book_tracks': book_tracks(con, 't.year = ? AND t.ess = 1', (y,)),
        'facts': rows(con.execute('''SELECT f.kind, f.title, f.body, f.source, f.episode, f.url, f.year,
                                            e.id, e.type, e.name
                                     FROM fact f LEFT JOIN entity e ON e.id = f.entity_id
                                     WHERE f.year = ? AND f.kind IN ('podcast', 'curiosity', 'award')
                                     ORDER BY COALESCE(e.weight, 0) DESC LIMIT 250''', (y,))),
    }


def list_detail(con, lid):
    l = con.execute('SELECT * FROM list WHERE id = ?', (lid,)).fetchone()
    if not l:
        return None
    d = dict(l)
    d['items'] = brief(con, f'''SELECT e.id, e.type, e.name, e.artist, e.year, li.rank, li.year AS item_year, li.note, {YT}, {SCARUFFI}
                               FROM list_item li JOIN entity e ON e.id = li.entity_id
                               WHERE li.list_id = ? ORDER BY li.rank IS NULL, li.rank, li.year LIMIT 2000''', (lid,))
    return d


def random_entity(con, type_):
    types = TYPE_FILTER.get(type_) or ('artist', 'album', 'song', 'label', 'genre', 'work')
    ph = ','.join('?' * len(types))
    r = con.execute(f'SELECT id FROM entity WHERE type IN ({ph}) AND weight >= 25 ORDER BY RANDOM() LIMIT 1',
                    types).fetchone()
    return {'id': r['id']} if r else {}


def cache_key(e):
    return f"{e['type']}|{norm(e['artist'] or '')}|{norm(e['name'])}"


def cached_img(e):
    with cache_db() as c:
        r = c.execute('SELECT url FROM img WHERE key = ?', (cache_key(e),)).fetchone()
    return r[0] if r else None


def deezer(path, **params):
    url = f'https://api.deezer.com/{path}?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'encarta/1.0'})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r).get('data') or []


def best(items, want, field):
    """El resultado cuyo nombre coincide con el buscado; si ninguno, el primero."""
    want = norm(want)
    for it in items:
        if norm(field(it)) == want:
            return it
    return items[0] if items else None


def find_img(e):
    """Foto de artista o portada en Deezer."""
    try:
        if e['type'] == 'artist':
            it = best(deezer('search/artist', q=e['name'], limit=5), e['name'], lambda x: x['name'])
            url = it and it.get('picture_xl')
            return None if not url or '/artist//' in url else url
        if e['type'] in WORK_TYPES:
            q = f"{e['artist'] or ''} {e['name']}".strip()
            if e['type'] != 'song':
                it = best(deezer('search/album', q=q, limit=5), e['name'], lambda x: x['title'])
                if it and it.get('cover_xl'):
                    return it['cover_xl']
            it = best(deezer('search/track', q=q, limit=5), e['name'], lambda x: x['title'])
            return it and it.get('album', {}).get('cover_xl')
    except (OSError, ValueError):
        return None
    return None


def entity_img(con, eid):
    e = ent(con, eid)
    if not e:
        return None
    url = e['info'].get('img') or e['info'].get('cover')
    if url:
        return {'img': url}
    key = cache_key(e)
    with cache_db() as c:
        r = c.execute('SELECT url, at FROM img WHERE key = ?', (key,)).fetchone()
        if r and (r[0] or time.time() - r[1] < RETRY):
            return {'img': r[0]}
    url = find_img(e)
    with cache_db() as c:
        c.execute('INSERT OR REPLACE INTO img VALUES (?,?,?)', (key, url, int(time.time())))
    return {'img': url}


def youtube(q):
    q = ' '.join(q.split())[:200]
    if not q:
        return {}
    with cache_db() as c:
        r = c.execute('SELECT id, title, at FROM yt WHERE q = ?', (q.lower(),)).fetchone()
        if r and (r[0] or time.time() - r[2] < RETRY):
            return {'id': r[0], 'title': r[1]}
    vid = title = None
    try:
        out = subprocess.run(['yt-dlp', '--no-warnings', '--flat-playlist', '--print', '%(id)s\t%(title)s',
                              f'ytsearch1:{q}'], capture_output=True, text=True, timeout=25).stdout.strip()
        if '\t' in out:
            vid, title = out.splitlines()[0].split('\t', 1)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    with cache_db() as c:
        c.execute('INSERT OR REPLACE INTO yt VALUES (?,?,?,?)', (q.lower(), vid, title, int(time.time())))
    return {'id': vid, 'title': title}


def stats(con):
    d = {t: n for t, n in con.execute('SELECT type, COUNT(*) FROM entity GROUP BY type')}
    d['facts'] = con.execute("SELECT COUNT(*) FROM fact WHERE kind IN ('podcast','curiosity')").fetchone()[0]
    d['books'] = rows(con.execute('SELECT id, title, author, url FROM mb_book ORDER BY title'))
    d['lists'] = con.execute('SELECT COUNT(*) FROM list').fetchone()[0]
    d['built'] = con.execute("SELECT v FROM meta WHERE k = 'built'").fetchone()[0]
    d['top'] = {t: brief(con, 'SELECT id, type, name, artist FROM entity WHERE type = ? ORDER BY weight DESC LIMIT 12',
                         (t,)) for t in ('artist', 'album', 'genre', 'label')}
    return d


# ── HTTP ─────────────────────────────────────────────────────────────────────

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def log_message(self, fmt, *args):
        if not self.path.startswith('/api/'):
            return
        super().log_message(fmt, *args)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/health':
            return self.send_json({'ok': os.path.exists(DB)})
        if not u.path.startswith('/api/'):
            return super().do_GET()
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        parts = u.path.strip('/').split('/')[1:]
        con = connect()
        try:
            if parts == ['search']:
                data = search(con, qs.get('q', ''), qs.get('type', 'all'), min(int(qs.get('limit', 60)), 300))
            elif parts[0] == 'entity' and len(parts) == 2 and parts[1].isdigit():
                data = entity_detail(con, int(parts[1]))
            elif parts[0] == 'year' and len(parts) == 2 and parts[1].isdigit():
                data = year_detail(con, int(parts[1]))
            elif parts[0] == 'list' and len(parts) == 2 and parts[1].isdigit():
                data = list_detail(con, int(parts[1]))
            elif parts == ['random']:
                data = random_entity(con, qs.get('type', 'all'))
            elif parts == ['stats']:
                data = stats(con)
            elif parts[0] == 'img' and len(parts) == 2 and parts[1].isdigit():
                data = entity_img(con, int(parts[1]))
            elif parts == ['yt']:
                data = youtube(qs.get('q', ''))
            else:
                return self.send_json({'error': 'ruta desconocida'}, 404)
            if data is None:
                return self.send_json({'error': 'no encontrado'}, 404)
            self.send_json(data)
        finally:
            con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8765)))
    ap.add_argument('--host', default=os.environ.get('HOST', '127.0.0.1'))
    a = ap.parse_args()
    if not os.path.exists(DB):
        raise SystemExit(f'No existe {DB}: ejecuta primero python3 -I build.py')
    print(f'Encarta en http://{a.host}:{a.port}/')
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
