---
title: "QA Predictivo: Cómo usar Machine Learning para anticipar bugs antes del deploy"
description: "Construí un predictor de defectos just-in-time, lo entrené con requests y Flask y lo evalué como se usaría en la práctica. Funciona. Solo que no como dicen las presentaciones de venta."
publishDate: 2026-11-03
lang: es
key: predictive-qa
tags:
  - QA
  - Machine Learning
  - CI/CD
  - Python
repo: https://github.com/douglasbonafe/predictive-qa
cover: /assets/blog/predictive-qa-es.jpg
cover_alt: "QA Predictivo: ordenar commits por riesgo de bug antes del deploy"
---

Todos los equipos de QA con los que trabajé tienen el mismo problema con distinto disfraz. Hay más cambios que atención para revisarlos. Alguien sube un PR de 400 líneas un jueves a las 17h, dos personas lo aprueban en once minutos, y el postmortem de la semana siguiente dice "pruebas insuficientes", como si las pruebas fueran un condimento que se echa encima.

QA predictivo es la idea de gastar esa atención mejor. Antes de que un commit llegue a producción, calculas qué tan probable es que traiga un bug y mandas los riesgosos a un segundo revisor, a una suite de pruebas más larga o a un rollout más lento. En la investigación se llama predicción de defectos just-in-time (JIT), y existe desde que Mockus y Weiss lo hicieron en Bell Labs en el año 2000.

Últimamente lo veo vendido por todos lados, casi siempre con un AUC de 0.85 en la diapositiva y ni una palabra de cómo se midió. Así que construí uno desde cero, lo corrí en dos codebases reales y lo medí como lo usaría un equipo. El código está aquí: [douglasbonafe/predictive-qa](https://github.com/douglasbonafe/predictive-qa).

Versión corta: funciona, es barato, y casi todo su poder viene de algo que puedes calcular con `git diff --stat`. La versión larga es más útil.

## Las tres piezas

Todo predictor JIT necesita etiquetas, features y un modelo. El modelo es la parte menos interesante.

### Etiquetas: ¿qué commits fueron malos?

No tienes una lista de "commits que causaron bugs". Nadie la tiene. Lo que tienes es una lista de commits que arreglaron algo, y con eso alcanza para ir hacia atrás.

El truco estándar es SZZ, por Śliwerski, Zimmermann y Zeller, que lo publicaron en 2005. Toma un commit de corrección. Mira las líneas que tuvo que borrar o editar. Corre `git blame` sobre esas líneas en la versión anterior. Quien las tocó por última vez introdujo el bug.

```python
def _links_for_fix(repo, fix, max_files):
    code = [f for f in fix.files if f.deleted > 0 and is_code_file(f.path)]
    if not code or len(code) > max_files:   # big "fixes" are usually refactors
        return []
    parent = fix.parents[0]
    found = set()
    for f in code:
        ranges = deleted_ranges(repo, parent, fix.sha, f.path)   # git diff -U0 -w
        found.update(blame_lines(repo, parent, f.path, ranges))  # git blame -w --porcelain
    return [Link(s, fix.sha, fix.timestamp) for s in found]
```

Es tosco. Las correcciones se detectan por palabras clave en el mensaje del commit, así que "fix typo in README" cuenta, y una corrección que solo agrega un null check que faltaba no culpa a nadie. Herbold y sus colegas lo auditaron en 2022 y encontraron que solo alrededor de la mitad de los commits que SZZ trata como correcciones de bugs realmente lo son. Esa es la calidad de etiqueta con la que trabaja todo el campo. La mantengo, y me lo recuerdo cada vez que leo los resultados.

Un detalle que importa más adelante: guardo *cuándo* quedó expuesto cada commit malo, no solo que lo fue. El timestamp de la primera corrección es lo que hace posible una evaluación honesta.

### Features: ¿cómo se ve un commit riesgoso?

Usé las 14 métricas de cambio de Kamei et al. (2013), que siguen siendo la referencia. Se agrupan en cinco:

- Tamaño: líneas agregadas, líneas borradas, tamaño de los archivos tocados.
- Difusión: por cuántos archivos, directorios y subsistemas se reparte el cambio, y qué tan parejo.
- Propósito: ¿el commit en sí es una corrección?
- Historial: cuántos desarrolladores tocaron esos archivos, cuánto pasó desde el último cambio, cuántos cambios previos.
- Experiencia: cuántos commits hizo el autor en total, recientemente y en ese subsistema.

Agregué una más de Rahman y Devanbu (2013): la cantidad de correcciones anteriores que tocaron los mismos archivos. El código que vive necesitando correcciones tiende a seguir necesitándolas.

Todo sale de una sola pasada por `git log --numstat`, del commit más viejo al más nuevo. La fila de cada commit se escribe antes de actualizar el estado acumulado, así que ningún commit ve su propio futuro. Hay un test para eso, porque es el tipo de bug que hace que todo se vea mejor y nadie lo nota.

### Modelo: regresión logística, casi siempre

Entrené regresión logística y gradient boosting con features en escala logarítmica y pesos de clase balanceados. Nada exótico. La regresión logística ganó con los datos que tenía, y tiene una ventaja real en una herramienta de CI: puedes explicar el score. "Este commit es riesgoso porque agrega muchas líneas a archivos que necesitaron cinco correcciones este año" es algo con lo que un revisor puede actuar. "El árbol dijo 0.71" no lo es.

## Cómo lo evalúas lo decide todo

Aquí es donde se caen la mayoría de las demos.

La forma perezosa es mezclar todos los commits, dividir 70/30 y usar las etiquetas que tienes hoy. Parece correcto. Está mal dos veces.

Primero, entrena con el futuro. Un split aleatorio pone commits de 2024 en entrenamiento y de 2019 en prueba. El modelo aprende patrones de un código que todavía no existía cuando se escribieron esos commits de prueba. En producción, el modelo solo va a puntuar los commits de mañana con el conocimiento de ayer.

Segundo, filtra etiquetas. Si entrenas con commits de 2020 usando la salida de SZZ de hoy, algunos están marcados como defectuosos por correcciones que llegaron en 2022. En 2020, al momento de entrenar, no había forma de saberlo.

Así que la evaluación del POC hace esto:

1. Folds móviles en orden temporal. Entrena con el primer 40% del historial y prueba con el 8% siguiente. Luego 48% y el 8% siguiente, y así cinco veces.
2. Etiquetas a la fecha. Un commit de entrenamiento solo cuenta como defectuoso si su corrección ya había llegado antes del corte de entrenamiento.
3. Nada de datos frescos en la prueba. El 20% más reciente del historial nunca se usa para probar, porque sus bugs todavía no se encontraron y casi todo ahí parece limpio.
4. Baselines. Cada modelo se compara con "revisar primero los commits más grandes" y "revisar primero los más chicos". Si el modelo no le gana a un ordenamiento, no se despliega.
5. Métricas de presupuesto. Se reporta el AUC, pero el número que importa es: si el equipo revisa el 20% de commits más riesgosos, ¿qué parte de los malos atrapa?

```python
for c in cutoffs:
    i, j = int(c * n), int((c + window) * n)
    train, test = df.iloc[:i], df.iloc[i:j]
    cutoff_ts = int(train["timestamp"].iloc[-1])
    y_train = labels_as_of(train, cutoff_ts)   # only fixes known at the cutoff
    y_test = y_final[i:j]                      # full hindsight for scoring
```

## Resultados en requests y Flask

Lo corrí en [psf/requests](https://github.com/psf/requests) y [pallets/flask](https://github.com/pallets/flask). Las dos son librerías de Python maduras, bien revisadas y con historiales largos. Quitando los commits que no tocan código (SZZ no puede etiquetarlos, y dejarlos hace que cualquier modelo parezca más listo), quedan 2.830 y 2.029 commits. SZZ marcó el 17,7% y el 20,7% como causantes de bugs, dentro del rango que Kamei reportó en sus proyectos.

Promedios de cinco folds móviles:

| | requests | flask |
|---|---|---|
| Orden aleatorio: bugs atrapados en el 20% superior | 19% | 22% |
| Regresión logística: bugs atrapados en el 20% superior | 34% | 41% |
| "Commit más grande primero": bugs atrapados en el 20% superior | 34% | 49% |
| AUC, regresión logística | 0.69 | 0.73 |
| AUC, commit más grande primero | 0.69 | 0.77 |
| AUC, regresión logística, **split mezclado** | 0.75 | 0.81 |

Lee esa tabla dos veces. Yo lo hice.

**El modelo duplica, más o menos, lo que atraparías al azar.** Revisar el quinto más riesgoso de los commits atrapa entre un tercio y dos quintos de los malos. Eso es real, y para una herramienta que cuesta unos segundos en el CI, es un buen negocio.

**Una baseline de una línea rinde igual.** Ordenar commits por líneas cambiadas empata con el modelo en requests y le gana en Flask. Miré qué queda cuando el tamaño se mantiene constante: dentro de cada cuartil de tamaño, el ranking del modelo es apenas mejor que una moneda, y un modelo entrenado sin las features de tamaño saca un AUC de 0.51. En estos dos codebases, todo lo que va más allá del tamaño es casi ruido.

**El split con fuga infla el AUC entre 6 y 8 puntos.** Mismo modelo, mismas features, mismos datos. Solo mezclado y con visión del futuro. 0.81 parece un producto. 0.73 parece una heurística. El 0.73 es el que va a aguantar en tu pipeline.

## La trampa de métricas que nadie pone en la diapositiva

Hay una segunda familia de métricas en esta literatura, llamada effort-aware. En lugar de "cuántos commits malos hay en el 20% superior", pregunta "cuántos commits malos encuentras leyendo el 20% de todas las líneas cambiadas". Suena más realista, porque los commits grandes cuestan más de revisar.

Y lo corres. "Commit más chico primero" encuentra el 78% de los commits malos en requests usando solo el 20% de las líneas. Impresionante, hasta que agregas la columna que nadie reporta: para llegar ahí abriste el 85% de todos los commits. No ahorraste tiempo de revisión. Solo revisaste casi todo, en un orden raro.

Yang et al. (2016) mostraron que rankers simples y no supervisados como este le ganan a los modelos supervisados en métricas effort-aware. Huang, Xia y Lo (2017) respondieron que, cuando cuentas cuántos commits tiene que abrir un desarrollador, el panorama se invierte. Mis números reproducen los dos papers en una sola tabla, lo cual es un buen recordatorio de que la métrica es una decisión de producto, no técnica. Elige el presupuesto que tus revisores realmente tienen y mide eso.

## Lo que yo pondría en producción

No un bloqueo de merge. Lewis et al. corrieron un predictor de bugs en todo Google en 2013 y no encontraron un cambio medible en el comportamiento de los desarrolladores. Los ingenieros ignoraron scores con los que no sabían qué hacer y en los que no confiaban. Ese paper debería ser lectura obligatoria para cualquiera que venda "AI quality gates".

Lo que funciona es el ruteo. El POC trae un workflow de GitHub Actions que reentrena con el historial del propio repo en cada PR (segundos para unos miles de commits), puntúa los commits del PR y escribe una tabla en el resumen del job:

```
| Commit                         | Risk         | Lines    | Why                                              |
|--------------------------------|--------------|----------|--------------------------------------------------|
| `bfc8f983` add `versionchanged` | 0.61 (low)  | +67/-11  | lines added, author recent activity, file size   |
| `329c32b9` fix dev              | 0.45 (low)  | +33/-36  | author recent activity, lines added, prior fixes |
```

Riesgo alto significa dos cosas: hace falta un segundo revisor, y corre la suite completa en lugar de los smoke tests. Nunca significa "este commit está mal". El umbral se ajusta para que lo cruce cerca del 20% de los commits, un presupuesto que el equipo puede absorber sin aprender a ignorarlo.

Y siendo honesto: si tu propio reporte de `pqa evaluate` muestra que el modelo no le gana a "commit más grande primero", despliega la baseline. Es una línea de bash, se explica en un postmortem y es casi todo el valor.

## Dónde están las ganancias de verdad

Que el tamaño domine no es una falla del ML. Es una afirmación sobre lo que contiene el historial de git. El log sabe qué tan grande es un cambio y quién lo escribió. No sabe:

- cuánto del código cambiado está cubierto por pruebas,
- si el CI estuvo inestable en ese camino la semana pasada,
- cuánto tiempo estuvo el PR en revisión y cuántos comentarios recibió,
- si el autor es dueño de ese módulo o está de visita,
- si el cambio toca un camino caliente en los traces de producción.

Esas son las señales que agregaría después, y todas están disponibles en una empresa normal. El diff de cobertura sale de tu test runner. Los datos de revisión vienen de la API de GitHub. La propiedad del código viene de CODEOWNERS. Los traces vienen de OpenTelemetry. El valor de un sistema de QA predictivo crece con cuánto de ese contexto le des, y con qué tan honestamente midas si está ayudando.

## Pruébalo en tu repo

```bash
pip install git+https://github.com/douglasbonafe/predictive-qa
pqa mine     --repo . --out history.csv
pqa evaluate --data history.csv
pqa train    --data history.csv --model model.pkl
pqa score    --repo . --model model.pkl --range origin/main..HEAD
```

Corre `evaluate` primero. Mira la fila "biggest commit first" antes de mirar el modelo. Si encuentras un codebase donde el modelo gana con claridad, quiero saberlo.

## Referencias

- Mockus, A., Weiss, D. M. *Predicting risk of software changes.* Bell Labs Technical Journal, 2000.
- Śliwerski, J., Zimmermann, T., Zeller, A. *When do changes induce fixes?* MSR 2005.
- Kamei, Y. et al. *A large-scale empirical study of just-in-time quality assurance.* IEEE TSE, 2013.
- Rahman, F., Devanbu, P. *How, and why, process metrics are better.* ICSE 2013.
- Lewis, C. et al. *Does bug prediction support human developers? Findings from a Google case study.* ICSE 2013.
- Yang, Y. et al. *Effort-aware just-in-time defect prediction: simple unsupervised models could be better than supervised models.* FSE 2016.
- Huang, Q., Xia, X., Lo, D. *Supervised vs unsupervised models: a holistic look at effort-aware just-in-time defect prediction.* ICSME 2017.
- Herbold, S. et al. *Problems with SZZ and features: an empirical study of the state of practice of defect prediction data collection.* Empirical Software Engineering, 2022.
