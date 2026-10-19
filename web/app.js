// Encarta — cliente. Rutas por hash:
//   #/                portada          #/e/<id>      ficha de entidad
//   #/year/<año>      año              #/lista/<id>  lista o chart
//   #/buscar?q=&t=    resultados       #/azar        entrada al azar
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const main = $('#main');
const toc = $('#toc');

const TYPES = {
  artist: 'Artista', album: 'Álbum', song: 'Canción', work: 'Disco o canción',
  label: 'Sello', genre: 'Género', year: 'Año',
};
const LINK_NAMES = {
  wikipedia: 'Wikipedia', rateyourmusic: 'RYM', discogs: 'Discogs', lastfm: 'Last.fm', musicbrainz: 'MusicBrainz',
  allmusic: 'AllMusic', bandcamp: 'Bandcamp', spotify: 'Spotify', youtube: 'YouTube', website: 'Web oficial',
  setlistfm: 'setlist.fm', soundcloud: 'SoundCloud', apple: 'Apple Music', deezer: 'Deezer', genius: 'Genius',
  metacritic: 'Metacritic', aoty: 'AOTY', sputnikmusic: 'Sputnikmusic',
};
const BLANK_IMG = /2a96cbd8b46e442fc41c2b86b821562f/;

// ── Utilidades ───────────────────────────────────────────────────────────────

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const text = (s) => esc(s).replace(/\*([^*\n]+)\*/g, '<i>$1</i>');
const stripHtml = (s) => String(s ?? '').replace(/<a [^>]*>Read more on Last\.fm<\/a>\.?/gi, '').replace(/<[^>]+>/g, '').trim();
const plural = (n, one, many) => `${n.toLocaleString('es')} ${n === 1 ? one : many}`;
// Botón ▶ del reproductor flotante: con `id` suena al momento; sin él, se busca `q` en YouTube al pulsar.
const play = ({ id, q, title, label = '▶' }) => (id || q
  ? `<button type="button" class="play" data-yt="${esc(id || '')}" data-q="${esc(q || '')}" data-title="${esc(title || q || '')}" title="Escuchar ${esc(title || q || '')}">${label}</button>`
  : '');
const playWork = (e, artist) => {
  const a = artist ?? e.artist ?? '';
  return ['album', 'song', 'work'].includes(e.type) || e.yt !== undefined
    ? play({ id: e.yt, q: `${a} ${e.name ?? e.title}`, title: `${a ? a + ' — ' : ''}${e.name ?? e.title}` }) : '';
};
const ytId = (url) => {
  const m = String(url || '').match(/(?:youtube\.com\/watch\?(?:.*&)?v=|youtu\.be\/)([\w-]{11})/);
  return m ? m[1] : null;
};
// Botón para escuchar el episodio de una nota: en el reproductor si es de YouTube, si no enlace externo.
const episode = (x) => {
  const id = ytId(x.url);
  const title = [x.source, x.episode].filter(Boolean).join(' · ') || 'Episodio';
  if (id) return play({ id, title, label: '▶ Episodio' });
  return x.url && x.source && !/wikidata|wikipedia|musicbrainz|scaruffi|albumoftheyear|sputnik|rollingstone/i.test(x.url)
    ? ` <a class="ext small" href="${esc(x.url)}" target="_blank" rel="noopener">Escuchar episodio</a>` : '';
};
const ext = (url, label) => (url ? `<a class="ext" href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>` : '');
const badge = (t) => `<span class="badge ${t}">${TYPES[t] || t}</span>`;
const chip = (c) => (c ? `<span class="chip" style="background:${esc(c)}"></span>` : '');
const years = (a, b) => (a ? (b && b !== a ? `${a}–${b}` : `${a}`) : '');

function link(e, label) {
  const name = label ?? e.name;
  if (!e || !e.id || (STATIC && !STATIC.ids.has(e.id))) return `<span class="nolink">${esc(name)}</span>`;
  return `<a href="#/e/${e.id}">${esc(name)}</a>`;
}
// Enlace a una lista; en la versión estática solo si se exportó.
function listLink(id, html, cls = '', title = '') {
  const attrs = `${cls ? ` class="${cls}"` : ''}${title ? ` title="${title}"` : ''}`;
  if (STATIC && !STATIC.lists.has(id)) return `<span${attrs}>${html}</span>`;
  return `<a${attrs} href="#/lista/${id}">${html}</a>`;
}
const yearLink = (y) => (y ? `<a href="#/year/${y}">${y}</a>` : '');
const artistOf = (e) => (e.artist ? ` <span class="muted">— ${esc(e.artist)}</span>` : '');

const cache = new Map();
async function api(path) {
  if (cache.has(path)) return cache.get(path);
  const d = STATIC ? await staticApi(path) : await getJson('/api/' + path);
  if (cache.size > 80) cache.delete(cache.keys().next().value);
  cache.set(path, d);
  return d;
}

async function getJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.status === 404 ? 'No encontrado' : `Error ${r.status}`);
  return r.json();
}

// ── Versión estática (GitHub Pages) ──────────────────────────────────────────
// build_static.py exporta las fichas a data/*.json y pone window.ENCARTA_STATIC = true en
// index.html. Sin servidor: la búsqueda va sobre data/index.json en el navegador, las fotos
// se piden a Deezer por JSONP y los temas sin vídeo abren la búsqueda de YouTube.

let STATIC = null;  // { rows, ids, lists, threshold }

async function loadStatic() {
  if (!window.ENCARTA_STATIC || STATIC) return;
  const [rows, stats] = await Promise.all([getJson('data/index.json'), getJson('data/stats.json')]);
  STATIC = {
    rows: rows.map(([id, type, name, artist, year, weight]) => ({ id, type, name, artist, year, weight, s: snorm(`${name} ${artist || ''}`), n: snorm(name) })),
    lists: new Set(stats.lists_exported),
    threshold: stats.threshold,
  };
  STATIC.ids = new Set(STATIC.rows.map((r) => r.id));
  STATIC.byId = new Map(STATIC.rows.map((r) => [r.id, r]));
}
// Misma normalización que norm() de serve.py.
const snorm = (s) => String(s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  .replace(/&/g, ' and ').replace(/’/g, "'").replace(/[^\p{L}\p{N}_\s]/gu, ' ').replace(/\s+/g, ' ').trim();
const TYPE_FILTER = { artist: ['artist'], album: ['album', 'work'], song: ['song', 'work'], label: ['label'], genre: ['genre'] };

async function staticApi(path) {
  const [p, query] = path.split('?');
  const qs = new URLSearchParams(query);
  const [kind, id] = p.split('/');
  if (kind === 'entity') return getJson(`data/e/${id}.json`);
  if (kind === 'year') return getJson(`data/y/${id}.json`);
  if (kind === 'list') return getJson(`data/l/${id}.json`);
  if (kind === 'stats') return getJson('data/stats.json');
  if (kind === 'search') {
    const q = snorm(qs.get('q'));
    const types = TYPE_FILTER[qs.get('type')];
    const limit = Number(qs.get('limit') || 60);
    const hits = STATIC.rows.filter((r) => q && r.s.includes(q) && (!types || types.includes(r.type)));
    hits.sort((a, b) => (b.n === q) - (a.n === q) || b.n.startsWith(q) - a.n.startsWith(q) || b.weight - a.weight);
    return { q, results: hits.slice(0, limit) };
  }
  if (kind === 'random') {
    const types = TYPE_FILTER[qs.get('type')];
    const pool = STATIC.rows.filter((r) => r.weight >= 25 && (!types || types.includes(r.type)));
    return { id: pool[Math.floor(Math.random() * pool.length)].id };
  }
  if (kind === 'img') return { img: await deezerImg(STATIC.byId.get(Number(id))) };
  return {};
}

function jsonp(url) {
  return new Promise((resolve) => {
    const cb = `dz${Date.now()}${Math.floor(Math.random() * 1e6)}`;
    const el = document.createElement('script');
    const done = (v) => { delete window[cb]; el.remove(); resolve(v); };
    window[cb] = (d) => done(d);
    el.onerror = () => done(null);
    el.src = `${url}&output=jsonp&callback=${cb}`;
    document.head.appendChild(el);
    setTimeout(() => done(null), 8000);
  });
}

// Foto de artista o portada en Deezer, como find_img() de serve.py.
async function deezerImg(e) {
  if (!e) return null;
  const pick = (items, name, f) => (items || []).find((x) => snorm(f(x)) === snorm(name)) || (items || [])[0];
  const q = encodeURIComponent(e.type === 'artist' ? e.name : `${e.artist || ''} ${e.name}`.trim());
  if (e.type === 'artist') {
    const it = pick((await jsonp(`https://api.deezer.com/search/artist?q=${q}&limit=5`))?.data, e.name, (x) => x.name);
    return it && it.picture_xl && !it.picture_xl.includes('/artist//') ? it.picture_xl : null;
  }
  if (!['album', 'song', 'work'].includes(e.type)) return null;
  if (e.type !== 'song') {
    const it = pick((await jsonp(`https://api.deezer.com/search/album?q=${q}&limit=5`))?.data, e.name, (x) => x.title);
    if (it && it.cover_xl) return it.cover_xl;
  }
  const it = pick((await jsonp(`https://api.deezer.com/search/track?q=${q}&limit=5`))?.data, e.name, (x) => x.title);
  return it?.album?.cover_xl || null;
}

// ── Notas al pie ─────────────────────────────────────────────────────────────

class Refs {
  constructor() { this.list = []; this.map = new Map(); }
  cite(f) {
    if (!f.source && !f.url) return '';
    const key = `${f.source}|${f.episode}|${f.url}`;
    let n = this.map.get(key);
    if (!n) {
      this.list.push(f);
      n = this.list.length;
      this.map.set(key, n);
    }
    return `<sup class="ref"><a href="#" data-jump="cite-${n}">[${n}]</a></sup>`;
  }
  html() {
    if (!this.list.length) return '';
    return `<ol class="references">${this.list.map((f, i) => {
      const what = [f.source && `<i>${esc(f.source)}</i>`, f.episode && `«${esc(f.episode)}»`].filter(Boolean).join(', ');
      return `<li id="cite-${i + 1}">${what || 'Fuente'}${f.url ? ' — ' + ext(f.url, hostOf(f.url)) : ''}${ytId(f.url) ? ' ' + episode(f) : ''}</li>`;
    }).join('')}</ol>`;
  }
}
function hostOf(u) {
  try { return new URL(u).hostname.replace(/^www\./, ''); } catch { return 'enlace'; }
}

// ── Construcción de artículos ────────────────────────────────────────────────

class Article {
  constructor() { this.parts = []; this.secs = []; this.refs = new Refs(); }
  add(html) { if (html) this.parts.push(html); return this; }
  section(title, body, count) {
    if (!body) return this;
    const id = 's-' + (this.secs.length + 1);
    this.secs.push({ id, title });
    const c = count ? `<span class="count">${count.toLocaleString('es')}</span>` : '';
    const closed = closedSections().includes(title) ? ' closed' : '';
    this.parts.push(`<section class="sec${closed}" data-title="${esc(title)}">
      <h2 id="${id}" class="sec-h" title="Plegar o desplegar"><span class="chev" aria-hidden="true"></span>${esc(title)}${c}</h2>
      <div class="sec-body">${body}</div></section>`);
    return this;
  }
  render() {
    this.section('Referencias', this.refs.html());
    if (this.secs.length > 2) {
      this.parts.splice(2, 0, `<div class="fold-all"><a href="#" data-fold="close">Plegar todo</a> · <a href="#" data-fold="open">Desplegar todo</a></div>`);
    }
    main.innerHTML = this.parts.join('');
    toc.innerHTML = this.secs.length > 1 ? `<h2>Contenido</h2><ol>
      <li><a href="#" data-jump="top">(Inicio)</a></li>
      ${this.secs.map((s, i) => `<li><a href="#" data-jump="${s.id}"><span class="n">${i + 1}</span>${esc(s.title)}</a></li>`).join('')}
    </ol>` : '';
    wireFilters();
    spy();
    fillImages();
  }
}

function infobox({ title, img, caption, rows, id, fallback }) {
  const body = rows.filter((r) => r && (r.head || (r[1] !== '' && r[1] != null))).map((r) => (r.head
    ? `<tr><td colspan="2" class="ib-head">${esc(r.head)}</td></tr>`
    : `<tr><th>${esc(r[0])}</th><td>${r[1]}</td></tr>`)).join('');
  const im = img && !BLANK_IMG.test(img)
    ? `<img class="ib-img" src="${esc(img)}" alt="" loading="lazy" onerror="this.remove()">`
    : id ? `<div class="ib-slot" data-img-for="${id}" data-fallback="${esc(fallback || '')}"></div>` : '';
  return `<aside class="infobox"><div class="ib-title">${esc(title)}</div>${im}
    ${caption ? `<div class="ib-caption">${caption}</div>` : ''}<table>${body}</table></aside>`;
}

const inline = (arr, f = (x) => link(x)) => (arr && arr.length ? `<ul class="inline">${arr.map((x) => `<li>${f(x)}</li>`).join('')}</ul>` : '');
const cols = (arr, f = (x) => link(x)) => (arr && arr.length ? `<ul class="cols">${arr.map((x) => `<li>${f(x)}</li>`).join('')}</ul>` : '');

function more(items, first, render, label = 'Mostrar') {
  if (!items.length) return '';
  const head = items.slice(0, first).map(render).join('');
  const rest = items.slice(first);
  return head + (rest.length ? `<details class="more"><summary>${label} ${rest.length} más</summary>${rest.map(render).join('')}</details>` : '');
}

function filterBox(target, placeholder = 'Filtrar…') {
  return `<div class="filter"><input type="search" data-filter="${target}" placeholder="${esc(placeholder)}"><label></label></div>`;
}
function wireFilters() {
  for (const inp of $$('[data-filter]')) {
    const box = $('#' + inp.dataset.filter);
    const label = inp.nextElementSibling;
    if (!box) continue;
    const items = $$('[data-f]', box);
    inp.addEventListener('input', () => {
      const q = norm(inp.value);
      let n = 0;
      for (const it of items) {
        const ok = !q || norm(it.textContent).includes(q);
        it.hidden = !ok;
        if (ok) n++;
      }
      label.textContent = q ? `${n} de ${items.length}` : '';
    });
  }
}
const norm = (s) => s.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();

function factList(facts, A, id, opts = {}) {
  if (!facts.length) return '';
  const rows = facts.map((f) => {
    const title = f.title || f.episode || 'Nota';
    const who = opts.entity && f.id ? `<span class="muted"> · ${badge(f.type)} ${link(f)}</span>` : '';
    const from = f.extra && f.extra.from ? `<div class="src">En la ficha de ${link({ id: f.extra.from_id, name: f.extra.from })}</div>` : '';
    const srcs = f.srcs || [f];
    const src = srcs.map((x) => [x.source, x.episode && x.episode !== title ? x.episode : null].filter(Boolean).map(esc).join(' · '))
      .filter(Boolean).join(' / ');
    return `<div data-f><dt>${text(title)}${f.year && !String(title).includes(f.year) ? `<span class="yr">(${f.year})</span>` : ''}${who}</dt>
      <dd>${f.body ? text(f.body) : ''}${srcs.map((x) => A.refs.cite(x)).join('')}${from}
        ${src || srcs.some((x) => x.url) ? `<div class="src">${src}${srcs.map(episode).join('')}</div>` : ''}</dd></div>`;
  });
  return (facts.length > 8 ? filterBox(id, 'Filtrar notas…') : '') + `<dl class="facts" id="${id}">${rows.join('')}</dl>`;
}

function sceneBlock(s) {
  const tracks = s.tracks.length ? `<h4>Discos y canciones citados (${s.tracks.length})</h4>
    <table class="wikitable"><tr><th class="num">Año</th><th>Artista</th><th>Título</th></tr>
    ${s.tracks.map((t) => `<tr><td class="num">${yearLink(t.year)}</td><td>${link({ id: t.artist_id, name: t.artist })}</td>
      <td>${play({ id: t.yt, q: `${t.artist} ${t.title}`, title: `${t.artist} — ${t.title}` })}${link(t, t.title)}${t.ess ? ' <span class="star" title="Destacado por el libro">★</span>' : ''}</td></tr>`).join('')}
    </table>` : '';
  const refs = s.refs.length ? `<h4>Citas del libro</h4>${s.refs.map((r) => `<blockquote>${esc(r.para || r.q)}
      <footer>${[r.chapter, r.page && `p. ${r.page}`].filter(Boolean).map(esc).join(' · ')}</footer></blockquote>`).join('')}` : '';
  return `<div class="scene">
    <h3>${chip(s.color)}${esc(s.name)} <span class="muted small">en <i>${esc(s.book.title)}</i> (${esc(s.book.author)})</span></h3>
    <div class="meta">${[s.family, years(s.start, s.end), s.place].filter(Boolean).map(esc).join(' · ')}
      ${s.link ? ' · ' + ext(s.link, 'ver en la web del libro') : ''}</div>
    ${s.aka.length ? `<div class="row"><b>También:</b> ${s.aka.map(esc).join(', ')}</div>` : ''}
    ${s.desc ? `<p>${text(s.desc)}</p>` : ''}
    ${s.notes.map((n) => `<p class="small"><b>${esc(n.chapter || 'Nota')}:</b> ${text(n.text)}</p>`).join('')}
    ${s.influences.length ? `<div class="row"><b>Influencias:</b> ${s.influences.map((x) => link(x)).join(', ')}</div>` : ''}
    ${s.labels.length ? `<div class="row"><b>Sellos y lugares:</b> ${s.labels.map((x) => link(x)).join(', ')}</div>` : ''}
    ${s.artists.length ? `<div class="row"><b>Artistas:</b> ${s.artists.map((x) => link(x) + (x.rating ? ` <span class="muted small">(${esc(x.rating)})</span>` : '')).join(', ')}</div>` : ''}
    ${s.tracks.length > 12 ? `<details class="more"><summary>Discos y canciones citados (${s.tracks.length})</summary>${tracks}</details>` : tracks}
    ${s.refs.length > 3 ? `<details class="more"><summary>Citas del libro (${s.refs.length})</summary>${refs}</details>` : refs}
  </div>`;
}

function sceneList(scenes) {
  return scenes.map((s) => `<details class="more"><summary>${chip(s.color)}<b>${esc(s.name)}</b>
      <span class="muted">(${years(s.start, s.end)}) — <i>${esc(s.book)}</i></span></summary>
      <p class="small">${text(s.desc || '')} ${s.id ? link(s, 'Ver ficha') : ''} ${s.link ? '· ' + ext(s.link, 'web del libro') : ''}</p></details>`).join('');
}

function bookTracks(tracks, showArtist) {
  if (!tracks.length) return '';
  const byBook = new Map();
  for (const t of tracks) {
    if (!byBook.has(t.book.title)) byBook.set(t.book.title, { book: t.book, items: [] });
    byBook.get(t.book.title).items.push(t);
  }
  return [...byBook.values()].map(({ book, items }) => `<h4><i>${esc(book.title)}</i> <span class="muted">(${esc(book.author)})</span></h4>
    <table class="wikitable"><tr><th class="num">Año</th>${showArtist ? '<th>Artista</th>' : ''}<th>Título</th><th>Escena</th><th>Dónde</th></tr>
    ${items.map((t) => `<tr><td class="num">${yearLink(t.year)}</td>
      ${showArtist ? `<td>${link({ id: t.artist_id, name: t.artist })}</td>` : ''}
      <td>${play({ id: t.yt, q: `${t.artist} ${t.title}`, title: `${t.artist} — ${t.title}` })}${link(t, t.title)}${t.ess ? ' <span class="star" title="Destacado por el libro">★</span>' : ''}</td>
      <td>${link({ id: t.scene_id, name: t.scene })}</td>
      <td class="small">${[...t.chapters, ...pagesText(t.pages)].map(esc).join(' · ')}</td></tr>`).join('')}
    </table>`).join('');
}
const pagesText = (pages) => (pages && pages.length ? [`p. ${pages.slice(0, 6).map((p) => p[2] || p[1]).join(', ')}${pages.length > 6 ? '…' : ''}`] : []);

function mentionsBlock(ms) {
  if (!ms.length) return '';
  const byBook = new Map();
  for (const m of ms) {
    if (!byBook.has(m.book)) byBook.set(m.book, []);
    byBook.get(m.book).push(m);
  }
  return [...byBook].map(([b, items]) => `<details class="more"><summary>Pasajes de <i>${esc(b)}</i> que lo nombran (${items.length})</summary>
    ${items.map((m) => `<blockquote>${esc(m.text)}<footer>p. ${m.page ?? '?'}</footer></blockquote>`).join('')}</details>`).join('');
}

function worksTable(works, id, artist) {
  if (!works.length) return '';
  return (works.length > 15 ? filterBox(id, 'Filtrar discografía (título, libro, podcast o lista)…') : '') + legend() + `<table class="wikitable" id="${id}">
    <tr><th class="num">Año</th><th>Título</th><th>Tipo</th><th>Fuentes</th></tr>
    ${works.map((w) => `<tr data-f><td class="num">${yearLink(w.year)}</td><td>${playWork(w, artist)}${link(w)}</td><td>${badge(w.type)}</td>
      <td>${sourcesCell(w.from)}</td></tr>`).join('')}
  </table>`;
}

// De dónde sale cada disco o canción: libros, podcasts y listas que lo citan.
const SHORT_PODCAST = {
  'The Ongoing History of New Music': 'Ongoing History', 'A History of Rock Music in 500 Songs': '500 Songs',
  'Hit Parade Music History and Music Trivia': 'Hit Parade', 'For the Record - The 70s': 'For the Record',
};
function sourcesCell(f) {
  if (!f) return '';
  const out = [
    ...f.books.map((b) => `<span class="src-tag book" title="Libro: ${esc(b.title)}">${esc(b.name)}</span>`),
    ...f.podcasts.map((p) => `<span class="src-tag pod" title="Podcast: ${esc(p.name)} (${plural(p.n, 'nota', 'notas')})">${esc(SHORT_PODCAST[p.name] || p.name)}${p.n > 1 ? ` <small>×${p.n}</small>` : ''}</span>`),
    ...f.lists.map((l) => listLink(l.id, `${esc(l.name)}${l.rank ? ` <small>#${l.rank}</small>` : ''}`, 'src-tag list', `Lista: ${esc(l.name)}${l.rank ? ` (puesto ${l.rank})` : ''}`)),
  ];
  if (f.n_lists > f.lists.length) out.push(`<span class="muted small">+${plural(f.n_lists - f.lists.length, 'lista', 'listas')}</span>`);
  return out.join(' ');
}
const legend = () => `<div class="legend small muted">Fuentes: <span class="src-tag book">libro</span> <span class="src-tag pod">podcast</span> <span class="src-tag list">lista</span></div>`;

function listsTable(lists) {
  if (!lists.length) return '';
  return `<table class="wikitable"><tr><th>Lista</th><th class="num">Puesto</th><th class="num">Año</th><th>Nota</th></tr>
    ${lists.map((l) => `<tr><td>${listLink(l.id, esc(l.name))}</td><td class="num">${l.rank ?? ''}</td>
      <td class="num">${yearLink(l.year || l.list_year)}</td><td class="small">${esc(l.note || '')}</td></tr>`).join('')}</table>`;
}

function entityTable(items, cols_ = ['year', 'name', 'artist']) {
  if (!items.length) return '';
  if (items.some((e) => e.from) && !cols_.includes('from')) cols_ = [...cols_, 'from'];
  const head = { year: '<th class="num">Año</th>', name: '<th>Título</th>', artist: '<th>Artista</th>', rank: '<th class="num">#</th>', type: '<th>Tipo</th>', from: '<th>Fuentes</th>' };
  const cell = {
    year: (e) => `<td class="num">${yearLink(e.year)}</td>`, name: (e) => `<td>${playWork(e)}${link(e)}</td>`,
    artist: (e) => `<td>${esc(e.artist || '')}</td>`, rank: (e) => `<td class="num">${e.rank ?? ''}</td>`, type: (e) => `<td>${badge(e.type)}</td>`,
    from: (e) => `<td>${sourcesCell(e.from)}</td>`,
  };
  return `${cols_.includes('from') ? legend() : ''}<table class="wikitable"><tr>${cols_.map((c) => head[c]).join('')}</tr>
    ${items.map((e) => `<tr>${cols_.map((c) => cell[c](e)).join('')}</tr>`).join('')}</table>`;
}

function linksRow(links) {
  if (!links) return '';
  return Object.entries(links).map(([k, u]) => ext(u, LINK_NAMES[k] || k)).join(' · ');
}

function coverage({ books = 0, podcast = 0, lists = 0, works = 0 }) {
  const bits = [];
  if (books) bits.push(plural(books, 'libro', 'libros'));
  if (podcast) bits.push(plural(podcast, 'nota de podcast', 'notas de podcast'));
  if (works) bits.push(plural(works, 'disco o canción', 'discos y canciones'));
  if (lists) bits.push(plural(lists, 'lista o chart', 'listas y charts'));
  return bits.length ? `Hay ${bits.join(', ').replace(/, ([^,]*)$/, ' y $1')}.` : 'No hay mucha información todavía.';
}

// Texto largo: el primer tramo a la vista y el resto plegado.
function longText(s, max = 700) {
  if (!s) return '';
  s = s.replace(/\s*User-contributed text is available under the Creative Commons.*$/s, '');
  if (s.length <= max * 1.3) return `<p>${text(s)}</p>`;
  const cut = s.lastIndexOf('. ', max) > max / 2 ? s.lastIndexOf('. ', max) + 1 : max;
  return `<p>${text(s.slice(0, cut))}</p><details class="more"><summary>Seguir leyendo</summary><p>${text(s.slice(cut).trim())}</p></details>`;
}

// En la fuente, «aliases» trae a veces artistas similares: se descartan los que coinciden.
function aliases(i) {
  const list = (Array.isArray(i.aliases) ? i.aliases : String(i.aliases || '').split(',')).map((x) => x.trim()).filter(Boolean);
  const similar = new Set((Array.isArray(i.similar) ? i.similar : String(i.similar || '').split(',')).map((x) => norm(x.trim())));
  return list.filter((a) => !similar.has(norm(a))).slice(0, 6).join(', ');
}

const uniqBooks = (...arrs) => new Set(arrs.flat().map((x) => (typeof x.book === 'string' ? x.book : x.book && x.book.title))).size;

// ── Fichas ───────────────────────────────────────────────────────────────────

function renderArtist(e) {
  const A = new Article();
  const i = e.info;
  const genres = e.genres.length ? e.genres.slice(0, 12) : e.album_genres;
  const labels = e.labels.length ? e.labels : e.album_labels;
  const tags = Array.isArray(i.tags) ? i.tags.slice(0, 8).join(', ') : '';
  const isGroup = /group|orchestra|choir/i.test(i.kind || '') || e.members.length > 1;
  A.add(`<h1>${esc(e.name)}</h1><div class="tagline">${badge('artist')}</div>`);
  A.add(infobox({
    title: e.name, img: i.img, id: e.id,
    rows: [
      ['Tipo', esc(i.kind === 'Group' ? 'Grupo' : i.kind === 'Person' ? 'Persona' : i.kind || '')],
      ['Origen', esc([i.origin, i.country].filter(Boolean).join(', '))],
      ['Años', i.begin || e.year ? `${i.begin ? esc(i.begin) : yearLink(e.year)}${i.end ? ' – ' + esc(i.end) : ''}` : ''],
      ['Géneros', inline(genres)],
      ['Etiquetas', esc(tags)],
      ['Sellos', inline(labels)],
      ['Miembros', inline(e.members.slice(0, 20))],
      ['Miembro de', inline(e.member_of)],
      ['Alias', esc(aliases(i))],
      ['Similares', esc(Array.isArray(i.similar) ? i.similar.slice(0, 6).join(', ') : i.similar || '')],
      ['Oyentes', i.listeners ? Number(i.listeners).toLocaleString('es') + ' (Last.fm)' : ''],
      ['Enlaces', linksRow(i.links)],
    ],
  }));
  const nBooks = uniqBooks(e.own_scenes, e.scenes, e.book_tracks);
  A.add(`<p class="lead"><b>${esc(e.name)}</b>${isGroup ? ' es un grupo' : ''}${i.origin || i.country ? ` (${esc(i.origin || i.country)})` : ''}${e.year ? `, en activo desde ${yearLink(e.year)}` : ''}.
    ${coverage({ books: nBooks, podcast: e.podcast.length, works: e.works.length, lists: e.charts.length })}</p>`);
  A.add(longText(stripHtml(i.bio)));
  if (i.wikipedia) A.add(`<details class="more"><summary>Texto de Wikipedia</summary><p class="longtext">${text(i.wikipedia)}</p></details>`);

  const books = [
    e.own_scenes.map(sceneBlock).join(''),
    e.scenes.length ? `<h3>Escenas en las que aparece</h3>${sceneList(e.scenes)}` : '',
    e.book_tracks.length ? `<h3>Discos y canciones citados</h3>${bookTracks(e.book_tracks)}` : '',
    e.mentions.length ? `<h3>Pasajes</h3>${mentionsBlock(e.mentions)}` : '',
  ].join('');
  A.section('En los libros', books, nBooks);
  A.section('En los podcasts', factList(e.podcast, A, 'f-podcast'), e.podcast.length);
  A.section('Discografía', worksTable(e.works, 'f-works', e.name), e.works.length);
  const charts = [
    e.charts.length ? `<table class="wikitable"><tr><th class="num">Año</th><th>Título</th><th>Lista</th><th class="num">Puesto</th><th>Nota</th></tr>
      ${e.charts.map((c) => `<tr><td class="num">${yearLink(c.year)}</td><td>${playWork(c, e.name)}${link(c)}</td><td>${listLink(c.list_id, esc(c.list))}</td>
      <td class="num">${c.rank ?? ''}</td><td class="small">${esc(c.note || '')}</td></tr>`).join('')}</table>` : '',
    e.chart_facts.length ? `<h3>Listas y charts (podcasts)</h3>${factList(e.chart_facts, A, 'f-chartfacts')}` : '',
    e.awards.length ? `<h3>Premios</h3>${factList(e.awards, A, 'f-awards')}` : '',
  ].join('');
  A.section('Charts, listas y premios', charts);
  const told = e.concerts.filter((c) => c.body);
  const named = e.concerts.filter((c) => !c.body && !told.some((t) => t.title === c.title));
  A.section('Conciertos', factList(told, A, 'f-concerts') + (named.length ? `${told.length ? '<h3>Otros conciertos</h3>' : ''}${inline(named, (c) => esc(c.title))}` : ''),
    told.length + named.length);
  if (e.xref.length) {
    A.section('Mencionado en otras fichas', `<p class="small muted">Notas de podcast sobre otros artistas que también hablan de ${esc(e.name)}.</p>
      <details class="more"><summary>Ver ${e.xref.length} notas</summary>${factList(e.xref, A, 'f-xref')}</details>`, e.xref.length);
  }
  A.render();
}

function renderWork(e) {
  const A = new Article();
  const i = e.info;
  const what = { album: 'un álbum', song: 'una canción', work: 'un disco o canción' }[e.type];
  A.add(`<h1>${esc(e.name)}${e.artist ? ` <span class="by">— ${esc(e.artist)}</span>` : ''}</h1>
    <div class="tagline">${badge(e.type)}</div>`);
  const scores = [
    i.scaruffi != null && ['Scaruffi', `<span class="score">${i.scaruffi}</span>/10`],
    i.aoty != null && ['AOTY crítica', `<span class="score">${i.aoty}</span>`],
    i.aoty_user != null && ['AOTY usuarios', `<span class="score">${i.aoty_user}</span>`],
    i.metacritic != null && ['Metacritic', `<span class="score">${i.metacritic}</span>`],
    i.sputnik != null && ['Sputnik', `<span class="score">${i.sputnik}</span>/5`],
  ].filter(Boolean);
  const fmt = (v) => (Array.isArray(v) ? v.map((x) => (typeof x === 'object' ? x.name || JSON.stringify(x) : x)).join(', ') : typeof v === 'object' ? '' : v);
  A.add(infobox({
    title: e.name, img: i.cover || i.img, id: e.id, fallback: e.artist_ref && e.artist_ref.info.img,
    caption: e.artist_ref ? `${TYPES[e.type]} de ${link(e.artist_ref)}` : '',
    rows: [
      ['Artista', e.artist_ref ? link(e.artist_ref) : esc(e.artist || '')],
      ['Publicación', yearLink(e.year)],
      ['Formato', esc(i.kind || '')],
      ['Sello', e.labels.length ? inline(e.labels) : esc(i.label || '')],
      ['Géneros', inline(e.genres.slice(0, 10))],
      ['Pistas', esc(i.tracks || '')],
      ['Del disco', i.album ? esc(i.album) : ''],
      ['Producción', esc(fmt(i.producers) || '')],
      ['Ingeniería', esc(fmt(i.engineers) || '')],
      ['País', esc(i.country || '')],
      ['Catálogo', esc(i.catalog || '')],
      scores.length ? { head: 'Puntuaciones' } : null,
      ...scores,
      ['Escuchar', play({ id: i.yt, q: `${e.artist || ''} ${e.name}`, title: `${e.artist ? e.artist + ' — ' : ''}${e.name}`, label: '▶ Reproducir' })],
      ['Enlaces', linksRow(i.links)],
    ],
  }));
  const nBooks = uniqBooks(e.book_tracks);
  A.add(`<p class="lead"><b>${esc(e.name)}</b> es ${what}${e.artist ? ` de ${e.artist_ref ? link(e.artist_ref) : esc(e.artist)}` : ''}${e.year ? ` publicado en ${yearLink(e.year)}` : ''}.
    ${coverage({ books: nBooks, podcast: e.podcast.length, lists: e.lists.length })}
    ${e.book_tracks.some((t) => t.ess) ? '<span class="star">★</span> Destacado como esencial en un libro.' : ''}</p>`);
  A.add(longText(stripHtml(i.desc)));
  if (i.scaruffi_note) A.add(`<p class="small muted">Scaruffi: ${esc(i.scaruffi_note)}</p>`);
  if (i.wikipedia) A.add(`<details class="more"><summary>Texto de Wikipedia</summary><p class="longtext">${text(i.wikipedia)}</p></details>`);
  A.section('En los libros', bookTracks(e.book_tracks), nBooks);
  A.section('En los podcasts', factList(e.podcast, A, 'f-podcast'), e.podcast.length);
  A.section('En listas y charts', listsTable(e.lists), e.lists.length);
  A.section(`Más de ${e.artist || 'este artista'}`, e.others.length ? inline(e.others, (o) => `${link(o)} <span class="muted small">${o.year || ''}</span>`) : '');
  A.render();
}

function renderLabel(e) {
  const A = new Article();
  A.add(`<h1>${esc(e.name)}</h1><div class="tagline">${badge('label')}</div>`);
  A.add(infobox({
    title: e.name,
    rows: [
      ['Artistas', e.artists.length ? String(e.artists.length) : ''],
      ['Discos', e.works.length ? String(e.works.length) : ''],
      ['En libros', inline(e.own_scenes.map((s) => ({ name: s.book.title })), (x) => `<i>${esc(x.name)}</i>`)],
      ['Escenas', inline(e.scenes_rel)],
    ],
  }));
  A.add(`<p class="lead"><b>${esc(e.name)}</b> es un sello discográfico (o lugar de la escena).
    ${coverage({ books: e.own_scenes.length, podcast: e.podcast.length, works: e.works.length })}</p>`);
  A.section('En los libros', e.own_scenes.map(sceneBlock).join('') +
    (e.scenes_rel.length ? `<h3>Escenas en las que aparece</h3>${inline(e.scenes_rel)}` : ''), e.own_scenes.length);
  A.section('En los podcasts', factList(e.podcast, A, 'f-podcast'), e.podcast.length);
  A.section('Artistas', cols(e.artists), e.artists.length);
  A.section('Discos', entityTable(e.works.sort((a, b) => (a.year || 9999) - (b.year || 9999)), ['year', 'name', 'artist', 'type']), e.works.length);
  A.render();
}

function renderGenre(e) {
  const A = new Article();
  const s0 = e.own_scenes[0];
  A.add(`<h1>${esc(e.name)}</h1><div class="tagline">${badge('genre')}</div>`);
  A.add(infobox({
    title: e.name,
    rows: [
      ['Familia', s0 ? chip(s0.color) + esc(s0.family || '') : ''],
      ['Periodo', s0 ? esc(years(s0.start, s0.end)) : ''],
      ['Lugar', s0 ? esc(s0.place || '') : ''],
      ['Libros', inline(e.own_scenes, (s) => `<i>${esc(s.book.title)}</i>`)],
      ['También', inline(e.aka)],
      ['Artistas', e.artists.length ? String(e.artists.length) : ''],
      ['Discos', e.works.length ? String(e.works.length) : ''],
    ],
  }));
  A.add(`<p class="lead"><b>${esc(e.name)}</b> es un género o escena musical${s0 && s0.start ? ` (${years(s0.start, s0.end)})` : ''}.
    ${coverage({ books: uniqBooks(e.own_scenes, e.similar_scenes), podcast: e.podcast.length, works: e.works.length })}</p>`);
  const books = e.own_scenes.map(sceneBlock).join('') +
    (e.similar_scenes.length ? `<h3>Escenas relacionadas</h3>${sceneList(e.similar_scenes)}` : '');
  A.section('En los libros', books, e.own_scenes.length + e.similar_scenes.length);
  A.section('En los podcasts', factList(e.podcast, A, 'f-podcast'), e.podcast.length);
  A.section('Lo mejor según RYM', e.rym.map((l) => `<h3>${listLink(l.id, esc(l.name))}</h3>
    ${entityTable(l.items, ['rank', 'name', 'artist', 'year'])}`).join(''));
  A.section('Artistas', cols(e.artists), e.artists.length);
  A.section('Discos', entityTable(e.works.slice(0, 150), ['year', 'name', 'artist', 'type']), e.works.length);
  A.render();
}

async function showEntity(id) {
  const e = await api('entity/' + id);
  document.title = `${e.name} — Encarta`;
  if (e.type === 'artist') return renderArtist(e);
  if (e.type === 'label') return renderLabel(e);
  if (e.type === 'genre') return renderGenre(e);
  return renderWork(e);
}

async function showYear(y) {
  const d = await api('year/' + y);
  document.title = `${y} — Encarta`;
  const A = new Article();
  A.add(`<h1>${y}</h1><div class="tagline">${badge('year')}</div>
    <div class="yearnav"><a href="#/year/${y - 1}">← ${y - 1}</a><a href="#/year/${y + 1}">${y + 1} →</a></div>`);
  const born = d.scenes.filter((s) => s.born);
  const active = d.scenes.filter((s) => !s.born);
  A.add(`<p class="lead">En <b>${y}</b> ${born.length ? `nacen ${plural(born.length, 'escena', 'escenas')} según los libros y ` : ''}siguen activas
    ${plural(active.length, 'escena', 'escenas')}. ${coverage({ podcast: d.facts.length, works: d.albums.length + d.songs.length })}</p>`);
  A.section('Escenas', (born.length ? `<h3>Nacen este año</h3>${sceneList(born)}` : '') +
    (active.length ? `<details class="more"><summary>En activo (${active.length})</summary>${sceneList(active)}</details>` : ''), d.scenes.length);
  A.section('Discos esenciales en los libros', bookTracks(d.book_tracks, true), d.book_tracks.length);
  A.section('Discos del año', entityTable(d.albums, ['name', 'artist', 'type']), d.albums.length);
  A.section('Canciones', entityTable(d.songs, ['name', 'artist']), d.songs.length);
  A.section('Charts', d.charts.map((c) => `<h3>${listLink(c.id, esc(c.name))}</h3>
    <ol class="plain">${c.items.map((x) => `<li value="${x.rank ?? ''}">${playWork(x)}${link(x)}${artistOf(x)}${x.note ? ` <span class="muted small">${esc(x.note)}</span>` : ''}</li>`).join('')}</ol>`).join(''), d.charts.length);
  A.section('Artistas que empiezan', cols(d.artists), d.artists.length);
  A.section('Notas de podcast', factList(d.facts, A, 'f-year', { entity: true }), d.facts.length);
  A.render();
}

async function showList(id) {
  const l = await api('list/' + id);
  document.title = `${l.name} — Encarta`;
  const A = new Article();
  A.add(`<h1>${esc(l.name)}</h1><div class="tagline"><span class="badge">Lista</span> ${esc({ musthear: 'Must hear', singles: 'Singles', charts: 'Charts' }[l.src] || l.src)}
    ${l.url ? ' · ' + ext(l.url, hostOf(l.url)) : ''}</div>`);
  A.add(`<p class="lead">${plural(l.items.length, 'entrada', 'entradas')}${l.year ? ` · ${yearLink(l.year)}` : ''}.</p>`);
  A.section('Entradas', filterBox('f-list') + `<table class="wikitable" id="f-list"><tr><th class="num">#</th><th>Título</th><th>Artista</th><th class="num">Año</th><th>Nota</th></tr>
    ${l.items.map((x) => `<tr data-f><td class="num">${x.rank ?? ''}</td><td>${playWork(x)}${link(x)}</td><td>${esc(x.artist || '')}</td>
      <td class="num">${yearLink(x.item_year || x.year)}</td><td class="small">${esc(x.note || '')}</td></tr>`).join('')}</table>`);
  A.render();
}

async function showSearch(q, t) {
  document.title = `${q} — Buscar — Encarta`;
  if (t === 'year' || /^\d{4}$/.test(q.trim())) {
    if (/^\d{4}$/.test(q.trim())) return go(`#/year/${q.trim()}`, true);
  }
  const d = await api(`search?q=${encodeURIComponent(q)}&type=${t}&limit=200`);
  const A = new Article();
  A.add(`<h1>Resultados de la búsqueda</h1><div class="tagline">«${esc(q)}» · ${esc(TYPES[t] || 'Todo')}</div>`);
  if (!d.results.length) {
    A.add('<p class="empty">No hay resultados. Prueba con menos palabras o con otro tipo.</p>');
  } else {
    A.add(`<ul class="results">${d.results.map((r) => `<li><div class="t">${link(r)} ${badge(r.type)}</div>
      <div class="sub">${[r.artist, r.year].filter(Boolean).map(esc).join(' · ')}</div></li>`).join('')}</ul>`);
  }
  A.render();
}

async function showHome() {
  document.title = 'Encarta';
  const s = await api('stats');
  toc.innerHTML = '';
  const n = (k) => (s[k] || 0).toLocaleString('es');
  const decades = [];
  for (let d = 1920; d <= 2020; d += 10) {
    decades.push(`<div><b>${d}s</b><div class="years">${Array.from({ length: 10 }, (_, i) => d + i).filter((y) => y <= 2026).map(yearLink).join(' ')}</div></div>`);
  }
  main.innerHTML = `<div class="home">
    <h1>Encarta</h1>
    <p class="welcome">${n('artist')} artistas, ${n('album')} álbumes, ${n('song')} canciones,
      ${n('label')} sellos y ${n('genre')} géneros, con ${n('facts')} notas de podcast, ${s.books.length} libros y ${n('lists')} listas.
      <br><span class="muted small">Datos de ${esc(s.built)} · <a href="#/azar">Abrir una entrada al azar</a></span>
      ${s.threshold ? `<br><span class="muted small">Versión reducida: ${n('exported')} fichas con más información; el resto aparece sin enlace.</span>` : ''}</p>
    <div class="portal">
      <section><h2>Artistas destacados</h2>${inline(s.top.artist)}</section>
      <section><h2>Discos destacados</h2>${inline(s.top.album, (x) => `${link(x)}${artistOf(x)}`)}</section>
      <section><h2>Géneros</h2>${inline(s.top.genre)}</section>
      <section><h2>Sellos</h2>${inline(s.top.label)}</section>
      <section><h2>Libros</h2><ul class="plain">${s.books.map((b) => `<li><i>${esc(b.title)}</i> <span class="muted">— ${esc(b.author)}</span> ${b.url ? ext(b.url, 'web') : ''}</li>`).join('')}</ul></section>
      <section><h2>Por año</h2>${decades.join('')}</section>
    </div></div>`;
}

async function fillImages() {
  for (const slot of $$('[data-img-for]', main)) {
    let url = null;
    try { url = (await api('img/' + slot.dataset.imgFor)).img; } catch { /* sin foto */ }
    url = url || slot.dataset.fallback;
    if (url && slot.isConnected && !BLANK_IMG.test(url)) {
      slot.outerHTML = `<img class="ib-img" src="${esc(url)}" alt="" onerror="this.remove()">`;
    }
  }
}

// ── Secciones plegables ──────────────────────────────────────────────────────
// Se recuerdan por título las secciones que el usuario pliega (p. ej. siempre «Referencias»).

function closedSections() {
  try { return JSON.parse(localStorage.getItem('encarta.closed') || '[]'); } catch { return []; }
}
function rememberSection(title, closed) {
  try {
    const set = new Set(closedSections());
    if (closed) set.add(title); else set.delete(title);
    localStorage.setItem('encarta.closed', JSON.stringify([...set]));
  } catch { /* sin almacenamiento: solo dura esta página */ }
}
document.addEventListener('click', (ev) => {
  const h = ev.target.closest('.sec-h');
  if (h && !ev.target.closest('a, button')) {
    const sec = h.parentElement;
    sec.classList.toggle('closed');
    rememberSection(sec.dataset.title, sec.classList.contains('closed'));
    return;
  }
  const f = ev.target.closest('[data-fold]');
  if (f) {
    ev.preventDefault();
    const close = f.dataset.fold === 'close';
    for (const sec of $$('.sec', main)) {
      sec.classList.toggle('closed', close);
      rememberSection(sec.dataset.title, close);
    }
  }
});

// ── Reproductor flotante ─────────────────────────────────────────────────────

const player = $('#player');
const frame = $('#player iframe');
let playingBtn = null;

function openPlayer(id, title, btn) {
  if (playingBtn) playingBtn.classList.remove('playing');
  playingBtn = btn || null;
  if (playingBtn) playingBtn.classList.add('playing');
  frame.src = `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0`;
  $('.pl-title', player).textContent = title || '';
  $('.pl-yt', player).href = `https://www.youtube.com/watch?v=${id}`;
  player.hidden = false;
  player.classList.remove('min');
}

function closePlayer() {
  frame.src = 'about:blank';
  player.hidden = true;
  if (playingBtn) playingBtn.classList.remove('playing');
  playingBtn = null;
}

document.addEventListener('click', async (ev) => {
  const b = ev.target.closest('button.play');
  if (!b) return;
  ev.preventDefault();
  if (!b.dataset.yt && STATIC) {
    window.open(`https://www.youtube.com/results?search_query=${encodeURIComponent(b.dataset.q)}`, '_blank', 'noopener');
    return;
  }
  if (!b.dataset.yt) {
    b.classList.add('loading');
    try {
      const r = await api('yt?q=' + encodeURIComponent(b.dataset.q));
      b.dataset.yt = r.id || '';
    } catch { /* sin conexión */ }
    b.classList.remove('loading');
    if (!b.dataset.yt) {
      b.classList.add('none');
      b.title = 'No se encontró en YouTube';
      return;
    }
  }
  openPlayer(b.dataset.yt, b.dataset.title, b);
});
$('.pl-close', player).addEventListener('click', closePlayer);
$('.pl-min', player).addEventListener('click', () => player.classList.toggle('min'));

// ── Navegación ───────────────────────────────────────────────────────────────

function go(hash, replace) {
  if (replace) {
    history.replaceState(null, '', hash);
    route();
  } else if (location.hash === hash) route();
  else location.hash = hash;
}

async function route() {
  const h = decodeURIComponent(location.hash.slice(1) || '/');
  const [path, query] = h.split('?');
  const p = path.split('/').filter(Boolean);
  closeSuggest();
  main.innerHTML = '<p class="loading">Cargando…</p>';
  try {
    await loadStatic();
    if (!p.length) await showHome();
    else if (p[0] === 'e') await showEntity(p[1]);
    else if (p[0] === 'year') await showYear(Number(p[1]));
    else if (p[0] === 'lista') await showList(p[1]);
    else if (p[0] === 'buscar') {
      const qs = new URLSearchParams(query);
      $('#q').value = qs.get('q') || '';
      $('#type').value = qs.get('t') || 'all';
      await showSearch(qs.get('q') || '', qs.get('t') || 'all');
    } else if (p[0] === 'azar') {
      const r = await api('random?type=' + $('#type').value + '&_=' + Date.now());
      return go(`#/e/${r.id}`, true);
    } else await showHome();
    window.scrollTo(0, 0);
  } catch (err) {
    main.innerHTML = `<h1>Error</h1><p class="empty">${esc(err.message)}</p>`;
    toc.innerHTML = '';
  }
}

document.addEventListener('click', (ev) => {
  const a = ev.target.closest('[data-jump]');
  if (!a) return;
  ev.preventDefault();
  const id = a.dataset.jump;
  if (id === 'top') return window.scrollTo({ top: 0, behavior: 'smooth' });
  const el = document.getElementById(id);
  if (!el) return;
  for (let d = el.closest('details'); d; d = d.parentElement.closest('details')) d.open = true;
  const sec = el.closest('.sec');
  if (sec) sec.classList.remove('closed');
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

let spyObs;
function spy() {
  if (spyObs) spyObs.disconnect();
  const links = new Map($$('a[data-jump]', toc).map((a) => [a.dataset.jump, a]));
  spyObs = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (!en.isIntersecting) continue;
      for (const a of links.values()) a.classList.remove('on');
      const a = links.get(en.target.id);
      if (a) a.classList.add('on');
    }
  }, { rootMargin: '-70px 0px -70% 0px' });
  for (const h of $$('h2[id]', main)) spyObs.observe(h);
}

// ── Búsqueda con sugerencias ─────────────────────────────────────────────────

const qInput = $('#q');
const sug = $('#suggest');
let sugItems = [];
let sugActive = -1;
let sugTimer;

function closeSuggest() { sug.hidden = true; sugActive = -1; }

async function suggest() {
  const q = qInput.value.trim();
  const t = $('#type').value;
  if (q.length < 2) return closeSuggest();
  const items = [];
  if (/^\d{4}$/.test(q)) items.push({ href: `#/year/${q}`, html: `${badge('year')} <b>${q}</b>` });
  if (t !== 'year') {
    const d = await api(`search?q=${encodeURIComponent(q)}&type=${t}&limit=12`);
    if (qInput.value.trim() !== q) return;
    for (const r of d.results) {
      items.push({ href: `#/e/${r.id}`, html: `${badge(r.type)} <span>${esc(r.name)}</span><span class="sub">${[r.artist, r.year].filter(Boolean).map(esc).join(' · ')}</span>` });
    }
  }
  items.push({ href: `#/buscar?q=${encodeURIComponent(q)}&t=${t}`, html: `<span class="sub">Buscar todas las coincidencias de «${esc(q)}»</span>` });
  sugItems = items;
  sugActive = -1;
  sug.innerHTML = items.map((x, i) => `<li data-i="${i}"><a href="${x.href}">${x.html}</a></li>`).join('');
  sug.hidden = false;
}

qInput.addEventListener('input', () => {
  clearTimeout(sugTimer);
  sugTimer = setTimeout(suggest, 140);
});
qInput.addEventListener('keydown', (ev) => {
  if (sug.hidden) return;
  if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
    ev.preventDefault();
    sugActive = (sugActive + (ev.key === 'ArrowDown' ? 1 : -1) + sugItems.length) % sugItems.length;
    $$('li', sug).forEach((li, i) => li.classList.toggle('active', i === sugActive));
  } else if (ev.key === 'Escape') closeSuggest();
});
qInput.addEventListener('blur', () => setTimeout(closeSuggest, 150));
$('#search').addEventListener('submit', (ev) => {
  ev.preventDefault();
  const q = qInput.value.trim();
  const t = $('#type').value;
  if (sugActive >= 0) return go(sugItems[sugActive].href);
  if (!q) return;
  if (/^\d{4}$/.test(q)) return go(`#/year/${q}`);
  go(`#/buscar?q=${encodeURIComponent(q)}&t=${t}`);
});
document.addEventListener('keydown', (ev) => {
  if (ev.key === '/' && document.activeElement !== qInput && !/input|select|textarea/i.test(document.activeElement.tagName)) {
    ev.preventDefault();
    qInput.focus();
    qInput.select();
  }
});

window.addEventListener('hashchange', route);
route();
