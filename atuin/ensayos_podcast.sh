# Podcast nuevo en ensayos: descarga (yt-dlp), transcribe (Whisper) y extrae los datos con Claude en vez de Gemini.
# URL: vídeo, lista o canal de YouTube, o feed RSS. Carpeta: nombre corto (p. ej. central_sonora); si ya existe, añade lo nuevo.
# Nombre: el del podcast para podcast.env (vacío = la carpeta). Máximo: nº de episodios a descargar (vacío = todos).
MAX="{{max_episodios}}"; NOMBRE="{{nombre}}"
cd "$HOME/gits/pollo/ensayos-musicales" && ~/.local/share/venvs/ensayos-musicales/bin/python scripts/podcast_nuevo.py "{{url}}" "{{carpeta}}" ${NOMBRE:+--nombre "$NOMBRE"} ${MAX:+--max "$MAX"}
echo "→ Después: atuin scripts run ensayos (incorpora los resúmenes y crea music_facts.db)"
