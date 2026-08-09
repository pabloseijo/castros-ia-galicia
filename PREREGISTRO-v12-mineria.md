# Preregistro: v12, minería de falsos positivos al estilo de Canedo

**Escrito el 2026-08-09 con dos de los cuatro barridos de v11p hechos —Lugo y A
Coruña— y sin conocer Ourense ni Pontevedra, luego sin conocer la media que fija
el listón.** Ese es el punto: el listón se define por una regla, no por un número
que ya se haya visto.

## Por qué esta y no otra

Lo medido hoy sobre v11p, en barridos completos y comparables:

| bloque | v7 | v11p |
| --- | ---: | ---: |
| Lugo | **`0,709`** | `0,618` |
| A Coruña | `0,424` | **`0,477`** |

**No es que v11p sea peor: es otro punto del compromiso.** Pierde donde v7 es
fuerte y gana donde v7 es débil, y con mucho más recall en A Coruña (`0,613`
contra `0,333`). Su carencia es **precisión**, medida: a recall emparejado
`0,714`, precisión `0,363` contra `0,703`.

La razón está diagnosticada en [[mas-positivos-sin-mas-fondo-empeora]]: v11p
entrena con **`26,7%` de positivos** y se despliega en un mundo con `0,73%`.

**La respuesta de la literatura a un problema de precisión no es más fondo
aleatorio: es minería de negativos duros.** Canedo et al. pasan de `5.678`
detecciones a `40` en castros, con `F1 66%`, minando los fallos del propio modelo.
Es la palanca mejor documentada para este objeto exacto.

## Qué se hace

1. Se recogen los **falsos positivos del barrido de v11p** a umbral `0,5`, que son
   sus errores reales en despliegue y no negativos inventados. Medidos hasta
   ahora: `202` en Lugo y `162` en A Coruña.
2. Se **criban por OSM** (`criba_osm.py`) para quedarse con los que tienen causa
   moderna identificable —cantera, polígono, terraplén, urbanización—. Una cantera
   es una cantera y no exige juicio arqueológico.
3. Se añaden al corpus de v11p como negativos duros **con peso `1`**.
4. Se entrena v12 y se barren los cuatro bloques.

## El peso es `1`, y esto es lo que separa v12 de v10

v10 puso peso `8` sobre negativos ya minados y **hundió el recall de castro de
`0,722` a `0,256`**, con `0,000` en O Val. Aquí la palanca es **la cantidad y la
especificidad de los negativos**, no un multiplicador. Si hiciera falta subir el
peso, sería otro experimento con su preregistro y su escala —`2`, `4`—, nunca un
valor suelto.

## El listón, reescrito el 2026-08-09 con el veredicto de v11p en la mano

> **Enmienda, y hay que declararla como tal.** Este preregistro se escribió
> fijando el listón contra «la media de v11p, que aún no se conoce». Ya se conoce:
> **`0,390`**, contra `0,512` de v7. **v11p está refutada**, así que un listón de
> `media(v11p) + 0,03 = 0,420` premiaría a v12 por batir a un modelo malo.
>
> Cambiar un listón después de ver datos es exactamente lo que un preregistro
> viene a impedir, así que esto se hace **una sola vez, por escrito y con motivo**:
> la referencia no cambia porque v12 vaya mal —v12 no existe todavía— sino porque
> **la referencia elegida resultó ser peor que el modelo en producción**.

Referencia: **v7 = `0,512`** de `F1` medio sobre los cuatro bloques, umbral `0,70`.

- **Éxito**: `F1` medio **`≥ 0,542`** (`+0,03` sobre v7) **y** recall de castro en
  validación `≥ 0,70`. Las dos condiciones.
- **Resultado útil aunque no gane**: entre `0,512` y `0,542`. Significa que la
  minería recupera lo que el desbalance de v11p había perdido —`0,122`— pero no
  añade nada sobre v7. Se reporta así, sin adornos.
- **Fracaso**: por debajo de `0,512`, o recall de castro bajo `0,70`. Si además
  cae el recall mientras sube la precisión, **es el patrón de v10** y la minería
  queda refutada también a peso `1`.

## Y una pregunta previa que ahora es obligatoria

Con v11p refutada por su proporción de positivos (`26,7%` contra `0,73%` de
despliegue), **minar sobre su corpus arrastra ese defecto**. Antes de v12 hay que
saber qué da **v13**, que es el mismo corpus con la proporción de v7 y está
entrenando.

**Si v13 recupera el nivel de v7, v12 debe minar sobre v13, no sobre v11p.** Y si
v13 no lo recupera, la proporción no era la causa y v12 hereda un problema sin
diagnosticar — en ese caso **no se lanza** hasta entenderlo.

## El riesgo, declarado antes y no después

**Canedo tenía dos arqueólogos** separando «falso positivo» de «yacimiento no
catalogado». Aquí no los hay, y el sustituto es la distancia al catálogo. Eso
significa que **algunos de los `364` negativos podrían ser castros inéditos, que
son exactamente lo que el proyecto busca**, y meterlos como negativos enseñaría al
modelo a no encontrarlos.

Tres mitigaciones, y ninguna lo elimina:

1. **La criba de OSM** deja solo los que tienen causa moderna visible.
2. A umbral `0,5` la precisión medida es `0,08`–`0,23`, así que la gran mayoría
   son error de verdad.
3. Los candidatos que la revisión visual marcó como prometedores —Cerceda, PO-2—
   se excluyen explícitamente con `--excluir`.

**El riesgo residual queda anotado en el corpus y en el registro, no escondido.**
Y si v12 gana, hay que comprobar que **no ha dejado de detectar los prometedores
de v11p**: si los pierde, ha aprendido justo lo que no debía.

## Coste

Un entrenamiento (`~2,5 h`) más cuatro barridos (`~5 h`). **No se lanza hasta que
terminen los de v11p**: el nodo tiene `7,3 GB` y hoy se han perdido tres barridos
por amontonar.

## Lo que este preregistro NO cubre

- El **desbalance de origen** (`26,7%` contra `0,73%`). La minería lo mitiga pero
  no lo corrige; corregirlo pide cortar mucho más fondo aleatorio, y es otro
  experimento.
- La **segunda ronda** de minería. Canedo itera; aquí se hace una ronda y se mide.
