# La configuración congelada — fase 2 del roadmap

Escrito el `2026-08-11`. **Este documento se escribe antes de mirar Portugal y no
se toca después.** Ese es todo su valor: si se pudiera reescribir tras ver el
resultado, no congelaría nada.

Lo que sigue es la configuración con la que se barrerá el conjunto de prueba
precintado, y el porqué de cada pieza. Nada de esto se elige ya sobre Portugal:
Portugal solo se mide.

---

## 1 · La configuración, en una tabla

| pieza | valor congelado | dónde se decidió |
| --- | --- | --- |
| **método** | **fusión por rango (RRF)** de cuatro modelos | validación, 4 bloques |
| miembros | `v7`, `v7last`, `v8`, `v12` | validación |
| `k` de RRF | `60` | valor estándar de la receta, **no ajustado** |
| **enlace** | `512 m` | validación |
| **celdas retenidas** (`K`) | `100` por bloque | validación |
| tolerancia de acierto | `500 m` | fijada desde el principio |
| **criba de falsos positivos** | **ninguna** | cerrada: ver §4 |
| canales de entrada | `7`, con `--dem-dir` activo | desbloqueado el 2026-08-11 |
| diezmado de densidad | `2,0 pt/m²` **solo en Portugal** | ver §5 |

Un solo número resume el punto de operación: **con `~257` fichas sobre los cuatro
bloques de validación, la fusión encuentra `113` de `214` castros.**

## 2 · Por qué la fusión y no el mejor modelo suelto

Por `F1` medio, el ganador es `v7` con `0,512`. Por eso el candidato natural era
congelar `v7` y acabar. **No es la decisión correcta**, y la razón es que el `F1`
no es la moneda de este proyecto.

Lo que cuesta dinero es la **ficha**: una persona mirando un recorte de terreno.
Así que la pregunta es *cuántos castros aparecen por cuántas fichas hay que
revisar*, y ahí el orden cambia:

| método | `200f` | `300f` | `450f` | `700f` |
| --- | ---: | ---: | ---: | ---: |
| **fusión por rango** | **97** | **120** | **145** | **202** |
| fusión por media | `94` | `117` | `144` | `201` |
| `v7` solo | `89` | `112` | `137` | `198` |
| `v8` solo | `89` | `116` | `136` | `192` |
| `v7last` solo | `93` | `113` | `132` | `183` |

La fusión gana **en los cuatro presupuestos**, entre `+4` y `+9` castros sobre
`v7`. Y el orden fusión > media > modelo suelto es el que se espera si la mezcla
aporta de verdad, no el que saldría del ruido.

**Una corrección que importa**: `fusion_por_rango.py` imprime *«NO APORTA»*
porque compara todos los métodos con el **mismo `K`**. Pero con el mismo `K`
cada método agrupa distinto y revisa un número distinto de fichas —`257` uno,
`297` otro—, así que esa comparación premia sin querer al método más disperso.
Es la misma trampa que comparar dos barridos con distinta cobertura. Comparados
a **igual número de fichas**, que es lo que se paga, la fusión gana.

## 3 · Por qué NO se congela `v17`, que entrenó el doble

`v17` corrió `40` épocas contra las `16` del resto. Quedó **octavo de diez**, con
`0,333` de `F1` medio contra los `0,512` de `v7`, y perdió en los cuatro bloques.

No es un detalle de calendario: es la prueba que faltaba. Ya se había medido
**brecha cero entre error de entrenamiento y de validación** —subajuste puro, no
sobreajuste—, y la lectura ingenua de eso es *«entrena más»*. Se entrenó más y
salió peor. Lo que queda en pie es el **suelo de Bayes**: la señal que hay en un
MDT de `1 m` sobre este problema tiene un techo, y estamos cerca.

## 4 · Por qué la criba va vacía, que es lo más incómodo

Se probaron **seis** instrumentos para separar los falsos positivos de los
castros reales. Ninguno lo consigue. El más llamativo alcanza `AUC 0,911`
distinguiendo castros de **terreno cualquiera** — y baja al azar cuando lo que
tiene que distinguir es castros de **los falsos positivos del propio modelo**.

Es la diferencia entre «esto no es un llano» y «esto no es un castro», y solo la
segunda sirve. Los falsos positivos **son paisaje con forma de castro**: no hay
un rasgo geométrico que los delate.

Congelar una criba que no criba solo añadiría una pieza que puede fallar. Va
vacía, y eso es un resultado, no una omisión.

## 5 · La única cosa que cambia en Portugal, y por qué

El vuelo de la DGT es de `10 pt/m²`; el PNOA español, de `1` a `2,7`. Si se
barriera Portugal a su densidad nativa y el resultado cayera, **no habría forma
de saber si el modelo no generaliza o si le cambiamos el sensor debajo**.

Por eso el barrido portugués lleva `--densidad-suelo 2.0`: se diezma a densidad
española. Es la única diferencia deliberada, y existe justo para que no haya dos.

## 6 · Lo que estas cifras NO son

**Ninguna cifra de este documento es una estimación insesgada de despliegue**, y
conviene decirlo antes y no después.

Todo lo de arriba —el checkpoint, el enlace, el `K`, elegir fusión sobre modelo
suelto— se decidió **mirando los cuatro bloques de validación**. Esa es la
función de un conjunto de validación y está bien empleado, pero significa que
`113 castros por 257 fichas` es un número **optimista por construcción**.

La primera estimación honesta será la de Portugal, y solo esa. Por eso el
precinto existe y por eso `detection_eval.py` se niega a evaluar contra él sin
`--romper-precinto "motivo"`.

**Lugo es el recordatorio**: su `F1 0,743` se dio por bueno como generalización
hasta que se vio que el umbral se había elegido contra ese mismo bloque. Un
bloque que el modelo nunca vio **no es conjunto de prueba** si se usa para elegir
un ajuste.

## 7 · Qué falsaría esto

Escrito ahora, para que no se pueda mover el listón después:

- **La fusión no aporta** si en Portugal empata o pierde contra `v7` solo a igual
  número de fichas. Se barrerán ambos, no solo el ganador.
- **El modelo no generaliza** si el rendimiento en Portugal cae por debajo de la
  mitad del de validación con la densidad ya igualada.
- **El suelo de Bayes es la explicación equivocada** si algún modelo posterior,
  con los mismos datos de entrada, se separa claramente de `0,5`.

## 8 · Lo que falta para ejecutar

Una sola cosa, y no es de ingeniería: **los ficheros LiDAR del norte de
Portugal**. El portal de la DGT exige cuenta y la descarga va por carrito, con
tope de `~200 km²` por sesión.

Todo lo demás está construido: `data/plan-descarga-portugal.tsv` tiene los `76`
rectángulos ordenados **por castros que aporta cada uno** —con `18` ya se cubre
medio precinto—, e `ingerir_portugal.sh` recoge, barre y borra cada petición sin
que el disco pase nunca de una a la vez.

Instrucciones de descarga: `DESCARGA-PORTUGAL.md`.
