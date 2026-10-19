#!/usr/bin/env bash
# Sube Encarta a pepecono (proyecto REPEAT_ONE, perfil `encarta`, puerto 8777).
#   ./deploy_pepecono.sh          sube código y encarta.db y reconstruye el contenedor
#   ./deploy_pepecono.sh --db     solo sube encarta.db (el servidor la recoge en caliente)
# La base se construye aquí con ./main.sh build: las fuentes viven en el portátil.

set -euo pipefail
cd "$(dirname "$0")"

HOST="${ENCARTA_HOST:-pepecono}"
DIR="${ENCARTA_DIR:-contenedores/repeat-one/services/encarta}"
REPO="${DIR%/services/encarta}"

[ -f encarta.db ] || { echo "Falta encarta.db: ejecuta ./main.sh build"; exit 1; }

ssh "$HOST" "mkdir -p $DIR/data"
# rsync escribe en un temporal y lo renombra: el servidor nunca lee una base a medias.
rsync -az --info=progress2 encarta.db "$HOST:$DIR/data/encarta.db"

if [ "${1:-}" != "--db" ]; then
    rsync -az --delete Dockerfile .dockerignore serve.py CLAUDE.md "$HOST:$DIR/"
    rsync -az --delete web/ "$HOST:$DIR/web/"
    ssh "$HOST" "cd $REPO && docker compose --profile encarta up -d --build encarta"
fi

ssh "$HOST" "curl -fsS http://localhost:8777/health" && echo && echo "Encarta en http://192.168.1.133:8777/"
