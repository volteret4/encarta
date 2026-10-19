# Añade una serie de MusicBrainz como colección must hear (vídeos y descripciones de Last.fm incluidos).
# Las claves se leen del entorno o de .encrypted.env (sops): no van en el comando.
cd "$HOME/gits/pollo/rym_lastfm" && "$HOME/Scripts/python_venv/bin/python" html_must_hear.py \
    --series "{{url_serie_musicbrainz}}" --name "{{nombre_de_la_coleccion}}" --youtube --lastfm-info
echo "→ Luego: atuin scripts run encarta"
