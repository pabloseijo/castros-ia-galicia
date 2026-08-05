# Instrucciones para quien trabaje en este nodo

> Este fichero existe para que la norma viaje con la máquina. Si estás ejecutando
> algo aquí, esto va contigo.

## Buscar literatura científica

**Este nodo es uno de los dos que ejecutan las búsquedas de artículos.** No es el
Mac quien las corre: es la Raspberry y `oval-server`, y pueden hacerlo a la vez
repartiéndose el fichero de temas.

Se usa **`scripts/lit_search.py`**, nunca una consulta escrita al vuelo:

```bash
python3 scripts/lit_search.py --topics temas.tsv --out data/lit-loquesea.tsv
python3 scripts/lit_search.py --query "hillfort detection LiDAR deep learning"
```

El fichero de temas es un TSV con dos columnas, `bucket` y `query`, para que cada
consulta quede atada al problema que pretende resolver.

### Las reglas están dentro del script, y son deliberadas

1. **Nunca ordena por citas.** Las citas miden popularidad del campo, no
   pertinencia. Ordenar por citas devolvió, para un problema de arqueología con
   LiDAR, una encuesta de imagen médica, otra de biosensores y una taxonomía del
   metaverso. Ordena por solapamiento léxico con la consulta.
2. **Exige DOI y publicación con nombre.**
3. **Descarta encuestas genéricas** salvo `--allow-surveys`.
4. **Excluye preprints** salvo `--include-preprints`.
5. **Semáforo por dominio, backoff y caché**: cortesía con APIs públicas, y
   reanudable, que aquí no es opcional.

### Lo que el script no hace

**Encontrar un candidato no autoriza a citarlo.** Citar exige leer el resumen o,
mejor, el texto completo. `lit_search.py` descubre en volumen; el filtrado
editorial se hace leyendo.

## Trabajo largo

- Todo proceso largo va con `nohup setsid ... < /dev/null &` y log propio: sin
  eso muere al cerrar la sesión SSH.
- Todo trabajo por lotes va **concurrente**, con semáforo cuando toque red, y
  **reanudable**: esta infraestructura se cae, y un proceso que solo escribe al
  final es un proceso que no existe.
- `pgrep -f <patrón>` **se auto-matchea** con el propio `bash -c` que lo lanza por
  SSH y da falsos «sigue vivo». Filtrar o comprobar `/proc/<pid>/cmdline`.

## Dónde está el proyecto

El repositorio canónico con git es **`~/Documents/CastrosIA` en el Mac**. Lo que
hay aquí es un workspace de ejecución: los datos pesados viven aquí, pero el
código se sincroniza desde el Mac. No es sitio para la única copia de nada.
