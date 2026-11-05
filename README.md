# Encarta

Una enciclopedia musical de consulta: buscas un artista, disco, canción, sello, género o año y reúne en una ficha notas, listas, charts y pasajes de libros.

## Para qué sirve

Para preparar un programa o un artículo, o por curiosidad: todo lo que sabemos de algo, en un solo sitio y cruzado entre fuentes.

[Versión pública de prueba](https://volteret4.github.io/encarta/), reducida a las fichas con más datos.

## Instalación individual

La web solo necesita Python 3. Los datos están en `encarta.db`, que no va en el repo: se construye con `build.py` a partir de tus propias bases. Sus rutas están en `PATHS`, dentro de `build.py`, y se pueden cambiar por entorno. Hace falta `node` para leer los libros.

```bash
git clone https://github.com/volteret4/encarta.git
```

```bash
cd encarta && ./main.sh
```

Construye la base y abre <http://127.0.0.1:8765/>. Si ya tienes una `encarta.db`:

```bash
./main.sh serve
```

Con Docker, deja la base en `data/encarta.db`:

```bash
docker build -t encarta .
```

```bash
docker run -d --name encarta --restart unless-stopped --user "$(id -u):$(id -g)" -v "$PWD/data:/data" -p 8777:8765 encarta
```

## Instalación desde REPEAT-ONE

Este módulo forma parte de [REPEAT-ONE](https://volteret4.github.io/repeat-one-web/), que permite elegir qué módulos instalar: [ver la instalación](https://github.com/volteret4/repeat-one-web#instalación). Allí se llama `encarta`.
