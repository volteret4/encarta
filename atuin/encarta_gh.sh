# Genera la versión reducida (fichas con relevancia >= 10) y la publica en la rama gh-pages del repo.
cd "$HOME/gits/pollo/encarta" && ./main.sh static && ./publish_gh_pages.sh "{{repo_github}}"
