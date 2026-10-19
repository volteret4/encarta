#!/usr/bin/env bash
# Da de alta (o actualiza) en atuin los comandos de esta carpeta:  ./atuin/instalar.sh
set -euo pipefail
cd "$(dirname "$0")"
declare -A DESC=(
  [encarta]="Reconstruye Encarta con los datos nuevos y la sube a pepecono"
  [encarta_gh]="Publica la versión reducida de Encarta en GitHub Pages"
  [libros]="Regenera un libro de Music_Books (citas, vídeos, portadas, discografías)"
  [must_hear_nueva]="Añade una serie de MusicBrainz como colección must hear"
  [must_hear_singles]="Actualiza las listas de singles de rym_lastfm"
  [rym_pendientes]="Muestra los charts de género de RYM que faltan por scrapear"
  [rym_generos]="Scrapea los charts de RYM de los subgéneros de un género padre"
  [ensayos]="Pipeline de ensayos: resúmenes, datos y music_facts.db"
)
for name in "${!DESC[@]}"; do
  atuin scripts delete -f "$name" >/dev/null 2>&1 || true
  atuin scripts new "$name" -d "${DESC[$name]}" -t arco --script "$name.sh" >/dev/null
  echo "✓ $name"
done
