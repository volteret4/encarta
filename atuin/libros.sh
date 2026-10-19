# Regenera un libro de Music_Books: citas, páginas, vídeos, portadas y discografías nuevas.
# Necesita LASTFM_API_KEY en el entorno para las portadas.
cd "$HOME/gits/pollo/Music_Books/{{carpeta_del_libro}}" && tools/build.sh --yt
echo "→ Revisa los DUDOSO de arriba, publica el libro (git push en su carpeta) y luego: atuin scripts run encarta"
