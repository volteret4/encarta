// Vuelca a JSON (stdout) el contenido de todas las webs de Music_Books.
// Carga cada index.html en un sandbox de node con un `window` vacío, ejecuta
// sus data/*.js en el mismo orden que el navegador y recoge el espacio de
// nombres (POSTPUNK, ROCK, JAZZ…) con sus escenas, capítulos, citas y menciones.
// Uso: node build/dump_books.js ~/gits/pollo/Music_Books > libros.json
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = process.argv[2];
if (!root) { console.error('uso: dump_books.js <carpeta Music_Books>'); process.exit(1); }

function title(html) {
  const m = html.match(/<title>([^<]*)<\/title>/i);
  return m ? m[1].trim() : '';
}

function loadBook(dir) {
  const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
  const ctx = { console };
  ctx.window = ctx;
  vm.createContext(ctx);
  const scripts = [...html.matchAll(/src="(data\/[^"]+\.js)"/g)].map((m) => m[1]);
  const extra = ['data/mentions.js', 'data/pages.js'].filter((s) => !scripts.includes(s));
  for (const s of [...scripts, ...extra]) {
    const f = path.join(dir, s);
    if (!fs.existsSync(f) || /covers\.js$|discos\.js$/.test(s)) continue;
    vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
  }
  const nsName = Object.keys(ctx).find((k) => ctx[k] && ctx[k].genres && typeof ctx[k].genres.values === 'function');
  if (!nsName) return null;
  const ns = ctx[nsName];
  const pick = (suffix) => ctx[nsName + '_' + suffix] || {};
  return {
    slug: path.basename(dir),
    ns: nsName,
    title: title(html),
    families: ns.FAMILIES || {},
    chapters: ns.chapters || [],
    book: ns.book && typeof ns.book === 'function' ? { parts: ns.book.parts, sections: ns.book.sections } : ns.book || null,
    best: ns.best || null,
    genres: [...ns.genres.values()],
    refs: pick('REFS'),
    yt: pick('YT'),
    mentions: pick('MENTIONS'),
    pages: pick('PAGES'),
  };
}

const out = [];
for (const d of fs.readdirSync(root).sort()) {
  const dir = path.join(root, d);
  if (!fs.existsSync(path.join(dir, 'index.html')) || !fs.existsSync(path.join(dir, 'data'))) continue;
  try {
    const b = loadBook(dir);
    if (b) out.push(b);
  } catch (e) {
    console.error(`${d}: ${e.message}`);
  }
}
process.stdout.write(JSON.stringify(out));
