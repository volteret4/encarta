# Actualiza las listas de singles (nº 1, year-end, Grammy, Los 40…): solo descarga las que faltan o están viejas.
cd "$HOME/gits/pollo/rym_lastfm" && "$HOME/.local/share/venvs/rym_lastfm/bin/python" html_singles.py
echo "→ Luego: atuin scripts run encarta"
