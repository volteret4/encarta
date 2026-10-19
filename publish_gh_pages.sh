#!/usr/bin/env bash
# Publica site/ (generado con build_static.py) en la rama gh-pages de un repo de GitHub.
#   ./publish_gh_pages.sh git@github.com:volteret4/encarta.git
# Cada publicación sustituye la anterior (rama huérfana con un solo commit, push forzado),
# para que el repo no acumule cientos de MB de JSON por cada actualización.
# En GitHub: Settings → Pages → «Deploy from a branch» → gh-pages / (root).

set -euo pipefail
cd "$(dirname "$0")"

REMOTE="${1:?Uso: $0 <url del repo de GitHub>}"
[ -f site/index.html ] || { echo "Falta site/: ejecuta ./main.sh static"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -r site/. "$TMP/"
git -C "$TMP" init -q -b gh-pages
git -C "$TMP" add -A
git -C "$TMP" commit -q -m "Encarta: versión estática $(date +%Y-%m-%d)"
git -C "$TMP" push -f "$REMOTE" gh-pages
echo "Publicado en la rama gh-pages de $REMOTE"
