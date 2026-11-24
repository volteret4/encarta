# Pipeline de ensayos: extrae con Claude los datos de las transcripciones nuevas, los incorpora a data/, premios y charts, y music_facts.db.
# Con Gemini, como antes: RESUMEN=gemini delante de ./main.sh. El venv va delante en el PATH (main.sh llama a python3 a secas).
cd "$HOME/gits/pollo/ensayos-musicales" && PATH="$HOME/.local/share/venvs/ensayos-musicales/bin:$PATH" ./main.sh
echo "→ Revisa los artistas nuevos con /revisar-lotes en Claude Code y luego: atuin scripts run encarta"
