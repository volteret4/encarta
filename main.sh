#!/usr/bin/env bash
# Encarta: reconstruye encarta.db a partir de los tres repos y arranca la web.
#   ./main.sh           construir y servir en http://127.0.0.1:8765/
#   ./main.sh build     solo construir
#   ./main.sh serve     solo servir (usa la encarta.db existente)
#   ./main.sh deploy    construir y subir a pepecono (REPEAT_ONE, http://192.168.1.133:8777/)
#   ./main.sh static    generar la versión reducida para GitHub Pages en site/ (MIN=10)
# Puerto: PORT=9000 ./main.sh

cd "$(dirname "$0")" || exit 1
PORT="${PORT:-8765}"

case "${1:-all}" in
    build)  python3 -I build.py ;;
    serve)  python3 -I serve.py --port "$PORT" ;;
    deploy) python3 -I build.py && ./deploy_pepecono.sh ;;
    static) python3 -I build_static.py --min "${MIN:-10}" ;;
    all)    python3 -I build.py && python3 -I serve.py --port "$PORT" ;;
    *)      echo "Uso: $0 [build|serve|deploy|static]"; exit 1 ;;
esac
