# Cuántos charts de género de RYM faltan por scrapear, por género padre.
cd "$HOME/gits/pollo/rym_lastfm" && python3 -I - <<'PY'
import json, re, sqlite3
tree = json.load(open('docs/must_hear/rym_charts/rym_genres.json'))
con = sqlite3.connect('file:db/must_hear_rym_new.db?mode=ro', uri=True)
done = {r[0] for r in con.execute('SELECT slug FROM collections c WHERE EXISTS '
                                  '(SELECT 1 FROM collection_albums ca WHERE ca.collection_id = c.id)')}
def flat(g):
    return [g] + [x for s in g.get('subgenres', []) for x in flat(s)]
def slug(url):
    m = re.search(r'/all-time/g:([^/]+)', url)
    return 'rym_chart_all_time' + ('_' + re.sub(r'[^a-z0-9]+', '_', m.group(1)).strip('_') if m else '')
rows = [(p['slug'], len(flat(p)), sum(slug(g['chart_url']) not in done for g in flat(p))) for p in tree]
for s, n, f in sorted(rows, key=lambda r: -r[2]):
    if f:
        print(f'{s:34} faltan {f:4} de {n}')
print(f'Total: faltan {sum(r[2] for r in rows)} de {sum(r[1] for r in rows)} géneros.')
PY
echo "→ Para seguir: atuin scripts run rym_generos (con uno de los géneros padre de arriba)"
