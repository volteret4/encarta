# Pipeline de ensayos: resúmenes con Gemini, incorporación a data/, premios y charts, y music_facts.db.
# main.sh llama a python3 a secas: se le pone delante el venv, que es el que tiene google-genai.
cd "$HOME/gits/pollo/ensayos-musicales" && PATH="$HOME/Scripts/python_venv/bin:$PATH" ./main.sh
echo "→ Revisa los artistas nuevos con /revisar-lotes en Claude Code y luego: atuin scripts run encarta"
