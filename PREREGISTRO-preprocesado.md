# Preregistro — los seis arreglos del preprocesado

**Escrito el 2026-08-10, antes de ejecutar nada.**

La lista de experimentos de la fase 1 está **cerrada y refutada**: v11p, v13, v12
y v14 probaron cuatro formas de darle más o mejor información al modelo y ninguna
batió el `F1 0,512` de v7. Esta es **otra lista, sobre otra parte del sistema**:
lo que ocurre entre la nube de puntos y el tensor.

La razón para mirar aquí está en [[diagnostico-del-preprocesado]] y es mecánica:
**un parapeto de castro son `0,5`–`1,5 m` de relieve**, y cada paso del
preprocesado puede borrarlo. Si se borra ahí, no hay arquitectura que lo
recupere.

---

## El orden de trabajo, y por qué no es «probarlos todos»

Cuatro de los seis cambian la **representación de entrada**, así que exigen
recortar el corpus y reentrenar: unas `6 h` cada uno. Probarlos por separado son
`24 h` de nodo. Antes de gastarlas se hace lo barato:

**Fase A — medir el mecanismo, sin GPU.** Cada arreglo afirma que *conserva señal
que hoy se pierde*. Eso se puede medir **sobre el DTM directamente**, sin
entrenar: si un cambio no mejora la relación entre el relieve del parapeto y el
ruido de fondo, no hay razón para reentrenar con él.

**Fase B — reentrenar solo lo que la fase A justifique.**

Dos de los seis no necesitan nada de esto porque **no tocan la entrada**:

- **Aumento en test** es postproceso del barrido: se mide sobre los barridos que
  ya existen.
- **La métrica sobre lo alcanzable** es aritmética sobre resultados existentes.

---

## Fase A — las medidas sin GPU

### A1 · Rasterización robusta

**Hipótesis**: el mínimo de los retornos es un estimador ruidoso, y con
`2 pt/m²` —dos muestras por celda— su varianza es del mismo orden que el objeto.
El percentil `10` conserva la superficie del suelo con menos ruido.

**Medida**: sobre `40` castros catalogados que el modelo detecta y `40` puntos de
terreno aleatorio, se construye el DTM de las dos formas y se compara:

- **relieve del parapeto**: rango intercuartílico del `LRM` dentro del recinto;
- **ruido de fondo**: desviación del `LRM` en terreno llano del mismo recorte;
- **la razón entre los dos**, que es lo que decide si el objeto se ve.

**Se confirma si** la razón sube en la mediana de los `40`. **Se refuta si** no
sube o baja.

### A2 · Relleno de huecos por interpolación

**Hipótesis**: el relleno por vecino más próximo fabrica mesetas con escalones
que el canal de pendiente lee como escarpes.

**Medida**: fracción de píxeles con pendiente `> 30°` que **desaparecen** al
rellenar por TIN en vez de por vecino, en recortes con más de un `10%` de huecos.
Si el relleno fabrica bordes, quitarlos debe reducir esa fracción.

### A3 · Normalización por escala física

**Hipótesis**: normalizar por percentiles de cada viñeta hace que el mismo
parapeto valga distinto según el desnivel del entorno.

**Medida**: para los mismos `40` castros, el valor del `LRM` en el parapeto tras
cada normalización, contra el desnivel total del recorte. **Se confirma si** con
la normalización actual hay correlación —el mismo objeto vale menos donde hay más
desnivel— y con la física desaparece.

### A4 · Clasificación de suelo

**Medida**: cuántos puntos añade la clase `3` y si el `LRM` del parapeto mejora
o empeora al incluirla, sobre los mismos `40`.

---

## Fase B — lo que se reentrenaría, y con qué listón

**Solo si la fase A da señal.** El corpus se recorta con los cambios que la
hayan pasado y se entrena **una** variante, no cuatro:

- **v15** = los arreglos de representación que superen la fase A.
- **v16** = v15 más el **canal de apertura**, que es el único con evidencia
  propia previa a favor y el único que cambia el número de canales.

**Listón**: el mismo de siempre, `F1 ≥ 0,542` de media en los cuatro bloques y
recall de castro `≥ 0,70`. **No se mueve.**

**Y una condición que no estaba en los preregistros anteriores**: si v15 o v16
ganan, hay que comprobar además que **no pierden castros que el conjunto
congelado sí encontraba**, con `conjunto_no_pierde.py`. La lección de anoche.

---

## Lo que se mide sin tocar nada

### B1 · Aumento en test

Promediar la puntuación de las ventanas que solapan sobre cada celda. Los
barridos existentes ya tienen ese solape, así que **se mide sobre lo que hay**.

**Se confirma si** sube el `F1` medio de los cuatro bloques del conjunto
congelado. Es la única de las seis que no puede empeorar el sistema, porque si no
sube no se aplica.

### B2 · La métrica sobre lo alcanzable

No es un arreglo del modelo: es **informar dos cifras** en vez de una. `F1` sobre
todo lo catalogado y `F1` sobre los castros que conservan relieve, con el
criterio de uso del suelo ya medido y publicado en [[el-arado-y-no-el-ladrillo]].

**No se sustituye la cifra oficial por la segunda.** Eso sería elegir el
resultado. Se publican las dos, y la que se compara con la literatura sigue
siendo la primera.

---

## Lo que NO se hace

- **No se toca el precinto.** Nada de esto se evalúa contra los `282`.
- **No se toca la red**: ni arquitectura, ni pérdida, ni encoder.
- **No se mueve el listón** por muy bien que pinte la fase A.
- **No se acumulan cambios sin medir**: si la fase A refuta un arreglo, ese
  arreglo no entra en v15 aunque «no haga daño».
