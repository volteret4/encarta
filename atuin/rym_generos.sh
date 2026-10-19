# Scrapea los charts de RYM de todos los subgéneros de un género padre (se salta los que ya están).
# Abre un navegador visible para pasar Cloudflare: ejecutar en el portátil.
cd "$HOME/gits/pollo/rym_lastfm" && "$HOME/Scripts/python_venv/bin/python" html_must_hear.py --rym-genre-all "{{genero_padre}}"
echo "→ Luego: atuin scripts run encarta"
