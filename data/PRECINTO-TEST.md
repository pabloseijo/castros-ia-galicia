
## 2026-08-10 — correccion de composicion (NO es una evaluacion)

Se apartan **71 castros gallegos** de los 353 del fichero, detectados al construir v14 porque 6 de ellos aparecian a `0 m` del entrenamiento de v11p. Estan en Ourense y Pontevedra; el LiDAR de la DGT portuguesa no los cubre, asi que contarian como fallos automaticos. El conjunto de prueba queda en **282 castros del norte de Portugal**.

No se ha evaluado ningun modelo contra ellos ni se ha mirado ninguna prediccion. Autorizado por Pablo. Ficheros: `data/precinto-portugal.tsv` y `data/precinto-DESCARTADOS-galicia.tsv`.

- **2026-08-23** — Fase 3 del roadmap. Configuracion congelada por escrito el 2026-08-11 (CONGELADO.md, commit 767f469) antes de tocar ningun dato portugues: fusion por rango RRF de v7+v7last+v8+v12, k=60, enlace 512 m, criba ninguna. Barrido completo y auditado: 18 ordenes, 4 modelos, recuentos identicos, 50.781 celdas, cero truncados. Fuga verificada: solo 3 negativos a menos de 500 m, ningun positivo. Verdad recortada a los 144 castros dentro de lo barrido. (verdad: `precinto-portugal-barrido.tsv`)

- **2026-08-23** — Segunda lectura: la primera uso umbrales de probabilidad (0.30-0.80) sobre una puntuacion RRF cuyo maximo es 0.0667, asi que era estructuralmente incapaz de detectar nada y no informo del modelo. Aqui los umbrales son cortes de rango que corresponden a presupuestos fijos de revision (top 100..3200 celdas), que es la moneda que fijo el congelado. NO se ha ajustado nada del modelo. (verdad: `precinto-portugal-barrido.tsv`)

- **2026-08-23** — Tercera lectura, correccion de cobertura: 15 de los 144 castros no tienen ninguna celda barrida a menos de 512 m -huecos de la nube LiDAR o borde de rectangulo- y contarlos como fallo mide la descarga, no el modelo. Aqui la verdad son los 129 que el barrido pudo ver. Sin ningun ajuste del modelo. (verdad: `precinto-portugal-cubiertos.tsv`)
