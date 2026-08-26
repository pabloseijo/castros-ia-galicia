# Preregistro v14 — quitar la confusión espacial, no los datos

**Escrito el 2026-08-09, antes de construir el corpus y antes de entrenar.**

## La hipótesis

v11p y v13 fallaron **no por la cantidad de positivos, ni por su proporción, ni
por su calidad** —las tres están refutadas— sino porque **el `53%` de sus
positivos vive en bloques de los que el modelo no ve ni una viñeta de fondo**.

Un paisaje que solo aparece dentro de viñetas de castro es un atajo: el modelo
puede acertar reconociendo el sitio en vez del yacimiento. En despliegue el atajo
desaparece —el barrido recorre **todas** las celdas del bloque, castro incluido—
y queda la permisividad que se midió.

| corpus | positivos en bloques sin fondo | `val` |
| --- | ---: | ---: |
| v7 | `3%` | `2%` |
| v11p / v13 | **`53%`** | **`72%`** |
| v12 | `3%` | `2%` |

El `72%` de `val` explica además la contradicción que quedó abierta: v11p sacaba
**mejor validación que v7** (`0,63` contra `0,55`) y **peor despliegue en los
cuatro bloques**. Su examen medía el atajo.

## El cambio, que es uno solo

**v14 = v11p menos los positivos que no tienen fondo en su propio bloque**, y
repartido de nuevo por bloques para que el examen tampoco lo tenga.

- Se conserva **todo el fondo**, incluido el de bloques sin castros: un negativo
  suelto no confunde nada, solo enseña.
- No se toca la proporción a propósito. v13 ya demostró que no era la causa, y
  fijarla ahora mezclaría dos cambios en un experimento.
- No se descarga ni se corta nada: las viñetas ya existen.

## Qué se predice, y con qué se compara

La comparación válida es el **despliegue en los cuatro bloques** —Lugo, A Coruña,
Ourense, Pontevedra—, no la validación, que es lo que este preregistro acusa de
estar contaminada en v11p.

| resultado | lectura |
| --- | --- |
| `F1 ≥ 0,542` | **confirma el diagnóstico y mejora a v7.** El dato sí era palanca; lo que sobraba era el atajo |
| `0,512`–`0,542` | confirma el diagnóstico, no da modelo mejor. Se congela v7 |
| `≈ 0,522` (como v11p) | **refuta**: la confusión espacial no era la causa |
| `< 0,512` | refuta, y además el recorte de positivos hizo daño por sí solo |

Listón de utilidad: **`F1 ≥ 0,542`** y **recall de castro `≥ 0,70`**, los mismos
que v11, v12 y v13. No se mueven.

## Lo que no se hace

- **No se mira el precinto.** Regla 15.
- **No se elige el umbral por bloque.** El mismo para los cuatro, como siempre.
- Si v14 gana, antes de darla por buena se comprueba que **no pierde ninguno de
  los castros que v7 sí detectaba**.
