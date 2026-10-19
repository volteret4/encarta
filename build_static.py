#!/usr/bin/env python3
"""
build_static.py — versión reducida de Encarta para GitHub Pages (sin servidor).

Exporta a site/ la web y, como JSON, las fichas con relevancia (weight) >= --min,
todos los años, las listas que no son «RYM Top» (esas ya salen en su género) y un
índice de búsqueda que el navegador carga entero. Las fichas son las mismas que
sirve serve.py; lo que queda fuera se muestra como texto sin enlace.

Uso: python3 -I build_static.py [--min 10] [--out site] [--jobs 8]
"""

import argparse
import json
import os
import shutil
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import serve  # noqa: E402

YEARS = range(1900, 2027)


def dump(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


def export_entities(args):
    out, ids = args
    con = serve.connect()
    for i in ids:
        dump(os.path.join(out, 'e', f'{i}.json'), serve.entity_detail(con, i))
    con.close()
    return len(ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min', type=int, default=10, help='relevancia mínima de las fichas exportadas')
    ap.add_argument('--out', default=os.path.join(HERE, 'site'))
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    a = ap.parse_args()
    t0 = time.time()

    if os.path.exists(a.out):
        shutil.rmtree(a.out)
    shutil.copytree(os.path.join(HERE, 'web'), a.out)
    data = os.path.join(a.out, 'data')
    for d in ('e', 'y', 'l'):
        os.makedirs(os.path.join(data, d))
    # GitHub Pages: sin Jekyll, que ignora lo que empieza por «_».
    open(os.path.join(a.out, '.nojekyll'), 'w').close()
    html = os.path.join(a.out, 'index.html')
    with open(html) as f:
        page = f.read()
    with open(html, 'w') as f:
        f.write(page.replace('<script src="app.js"></script>',
                             '<script>window.ENCARTA_STATIC = true;</script>\n<script src="app.js"></script>'))

    con = serve.connect()
    rows = con.execute('SELECT id, type, name, artist, year, weight FROM entity WHERE weight >= ? '
                       'ORDER BY weight DESC', (a.min,)).fetchall()
    dump(os.path.join(data, 'index.json'), [list(r) for r in rows])
    print(f'índice: {len(rows)} fichas')

    lists = [r[0] for r in con.execute("SELECT id FROM list WHERE name NOT LIKE 'RYM Top%'")]
    for lid in lists:
        dump(os.path.join(data, 'l', f'{lid}.json'), serve.list_detail(con, lid))
    print(f'listas: {len(lists)}')

    for y in YEARS:
        dump(os.path.join(data, 'y', f'{y}.json'), serve.year_detail(con, y))
    print(f'años: {YEARS.start}-{YEARS.stop - 1}')

    # Las cifras de portada, de lo que lleva esta versión (no de la base completa).
    stats = serve.stats(con)
    counts = {t: 0 for t in ('artist', 'album', 'song', 'work', 'label', 'genre')}
    for r in rows:
        counts[r[1]] += 1
    con.execute('CREATE TEMP TABLE exported (id INTEGER PRIMARY KEY)')
    con.executemany('INSERT INTO exported VALUES (?)', [(r[0],) for r in rows])
    facts = con.execute("SELECT COUNT(*) FROM fact WHERE kind IN ('podcast', 'curiosity') "
                        "AND entity_id IN (SELECT id FROM exported)").fetchone()[0]
    stats.update(counts, facts=facts, lists=len(lists), threshold=a.min, lists_exported=lists)
    dump(os.path.join(data, 'stats.json'), stats)
    con.close()

    ids = [r[0] for r in rows]
    chunks = [(data, ids[i::a.jobs]) for i in range(a.jobs)]
    with Pool(a.jobs) as pool:
        done = sum(pool.map(export_entities, chunks))
    print(f'fichas: {done}')

    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(a.out) for f in fs)
    files = sum(len(fs) for _, _, fs in os.walk(a.out))
    print(f'listo → {a.out}: {files} ficheros, {size / 1e6:.0f} MB, {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
