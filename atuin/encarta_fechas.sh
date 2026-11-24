# Busca en MusicBrainz y Discogs el año de los discos y canciones de Encarta sin fecha (podcasts y libros; --todo = también listas),
# lo guarda en cache.db y reconstruye y sube Encarta. Tarda ~3 s por canción; se puede cortar y relanzar.
cd "$HOME/gits/pollo/encarta" && python3 -I fechas.py {{opciones}} && ./main.sh deploy
