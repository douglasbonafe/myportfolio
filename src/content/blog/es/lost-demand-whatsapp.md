---
title: "Demanda perdida: cómo medir las ventas que la tienda nunca hizo, a partir de las conversaciones de WhatsApp"
description: "La venta es solo la demanda que la tienda logró atender. El resto está en las conversaciones de WhatsApp. Aquí está la matemática para convertir esas conversaciones en ingreso perdido, demanda real, pronósticos, elasticidades y alertas de quiebre de stock, con un script que puedes ejecutar."
publishDate: 2026-11-27
lang: es
key: lost-demand-whatsapp
tags:
  - Retail Analytics
  - Forecasting
  - Estadística
  - Python
cover: /assets/blog/lost-demand-whatsapp-es.jpg
cover_alt: "Demanda perdida: 18 ventas registradas frente a 22,3 unidades de demanda real, con el ingreso perdido por producto"
---

La semana pasada escribí al WhatsApp de varias tiendas de electrónica de Paraguay, haciéndome pasar por cliente. Algunas tenían un bot que no sabía responder una pregunta sobre stock. Otras me derivaron a "un asesor mañana". Algunas nunca respondieron. Ninguna resolvió mi problema.

Nada de eso aparece en su reporte de ventas. Una venta que no ocurrió no deja ninguna fila en el ERP. Pero sí dejó un rastro: escribí exactamente qué quería comprar, a qué hora, y nadie respondió.

Estoy construyendo un agente de ventas por WhatsApp para tiendas, y el producto más interesante resultó ser el dato que recoge en el camino. Este post es la matemática detrás de eso. Todos los números de abajo salen de [un script que puedes ejecutar](/assets/blog/lost_demand.py), con datos sintéticos y semilla fija. Nada de esto es resultado de un cliente.

## La venta es demanda censurada

Cuando un producto se queda sin stock, la venta registrada cae a cero. La gente sigue pidiéndolo. En estadística esto se llama dato censurado: observas `min(demanda, stock)`, nunca la demanda en sí.

Si pronosticas el mes siguiente a partir de las ventas, subestimas justamente los productos que más faltan. Compras menos. Vuelven a faltar. El error se alimenta solo.

El efecto no es chico. El estudio mundial sobre quiebres de stock hecho en 2002 para [FMI, GMA y CIES](https://www.fmi.org/newsroom/news-archive/view/2002/10/14/new-industry-study-explores-root-causes-of-global-out-of-stock-dilemma) encontró una tasa promedio de quiebre de 8,3%. Frente a uno, el 31% de los clientes se va a otra tienda, el 26% cambia de marca y el 9% no compra nada.

Una tienda física no ve nada de esto, porque el cliente se va sin decir una palabra. En un canal de conversación es distinto. El cliente escribe lo que quería.

## Paso cero: cada conversación se convierte en un evento

Ninguna fórmula funciona sobre texto suelto. El agente, o un clasificador a su lado, tiene que convertir cada conversación en un registro:

| Campo | Ejemplo |
|---|---|
| `first_msg_ts`, `first_reply_ts` | 2026-11-20 22:14, 2026-11-21 09:02 |
| `product_id`, `quantity`, `offered_price` | SKU del ERP, 1, US$ 820 |
| `in_stock` | no |
| `outcome` | venta, abandono, sin respuesta |
| `loss_reason` | sin stock, precio, demora, fuera de catálogo, competidor |
| `handled_by` | agente, humano, nadie |

Dos detalles pesan más de lo que parece. La unidad de análisis es el par conversación y producto, porque una conversación puede tratar sobre tres productos. Y solo las conversaciones con intención de compra entran en el denominador de la conversión. Una consulta sobre garantía contada como venta perdida hunde todas las tasas.

## Ingreso perdido, bien calculado

La versión tentadora es "sumar el precio de todo lo que no vendimos". Está mal, porque no todo el que pregunta compraría, aun con stock y respuesta inmediata. Multiplica por la probabilidad real de venta:

```
R_p = N_p × ĉ_p × q̄_p × P_p

N_p   conversaciones del producto p perdidas por quiebre de stock, demora o fuera de catálogo
ĉ_p   tasa de conversión de p cuando había stock y alguien respondió
q̄_p   unidades promedio por venta
P_p   precio
```

Las pérdidas por precio quedan fuera de esta suma. Ahí la tienda hizo su parte y el cliente dijo que no. Eso es un tema de elasticidad, más abajo.

### No confíes en una tasa hecha con seis conversaciones

Un producto con 6 conversaciones atendidas y 2 ventas convierte 33%. Eso es ruido. Encoge la tasa de cada producto hacia la de su categoría, con una priori Beta:

```
ĉ_p = (ventas_p + α × c_categoría) / (atendidas_p + α)
```

`α` es cuántas conversaciones vale la categoría. Con `α = 20`, un producto necesita unas 20 conversaciones propias antes de que domine su propia tasa.

Smartphones convirtiendo 14%, un mes:

| Producto | Atendidas | Ventas | Tasa bruta | Tasa encogida | Conversaciones perdidas | Ingreso perdido |
|---|---|---|---|---|---|---|
| Phone A 128GB, US$ 820 | 100 | 18 | 18,0% | 17,3% | 40 | US$ 5.685 |
| Phone B 256GB, US$ 1.150 | 6 | 2 | 33,3% | 18,5% | 4 | US$ 849 |
| Cargador 30W, US$ 25, 1,4 un./venta | 60 | 21 | 35,0% | 29,8% | 13 | US$ 135 |

Total: US$ 6.670. Con la tasa bruta, la pérdida del Phone B habría salido 80% mayor, en base a seis conversaciones.

## Demanda real: suma lo que ocultó el quiebre de stock

```
D = ventas observadas + N_quiebre × ĉ × q̄
```

El Phone A vendió 18 unidades y perdió 25 conversaciones por falta de stock. Al 17,3%, son 4,33 unidades ocultas. Demanda real: 22,3 unidades, 24% más de lo que dicen las ventas. Ese es el número que debe usar la próxima orden de compra.

Sin datos de conversación, el atajo clásico es `ventas / fracción de días con stock`. Con 22 de 30 días con stock, da 24,5 unidades. La diferencia viene de su supuesto oculto: que la demanda en los días sin stock es igual a la de los días normales. La conversación no supone nada. Vio la demanda ocurrir.

## Pronóstico: elige el método según cómo se vende el producto

Pronostica sobre la demanda real, nunca sobre las ventas. Después:

- Pocas semanas de historia, sin tendencia: suavizado exponencial simple, `ŷ(t+1) = ŷ(t) + a × (y(t) − ŷ(t))`.
- Tendencia y estacionalidad: Holt-Winters. Para estacionalidad anual con datos semanales necesitas dos años de historia, o vas a confundir un buen año con el efecto del Black Friday.
- Productos de baja rotación, que son la mayor parte de un catálogo de electrónica: Croston (1972) o, mejor, SBA.

Croston mantiene dos series suavizadas, que se actualizan solo cuando hay venta: el tamaño de la venta `z` y el intervalo entre ventas `p`. El pronóstico es `z / p`. Syntetos y Boylan (2005) mostraron que está sesgado hacia arriba y lo multiplicaron por `(1 − a/2)`. Eso es SBA.

En un producto sintético de baja rotación que vende en el 35% de las semanas (demanda real de 0,875 unidades por semana), entrenado en 78 semanas y probado en las 26 siguientes:

| Método | Pronóstico por semana | Sesgo en el período de prueba | WAPE |
|---|---|---|---|
| Suavizado simple | 1,202 | +48,8% | 1,50 |
| Croston | 1,010 | +25,1% | 1,39 |
| SBA | 0,909 | +12,6% | 1,35 |

Un WAPE mayor a 1 parece un error, pero no lo es: un pronóstico constante falla en cada semana en cero. En demanda intermitente, la métrica que decide es el sesgo, porque el sesgo se convierte en stock parado o en quiebres. El de SBA es casi cuatro veces menor.

Y la regla que vale para todos: ningún pronóstico llega al cliente sin backtest.

## Elasticidad: precio y el real brasileño

Las tiendas de frontera en Paraguay le venden a brasileños, así que el tipo de cambio mueve la demanda tanto como el precio. Una regresión log-log con términos de Fourier para la estacionalidad:

```
ln D(t) = β0 + β1 ln P(t) + β2 ln E(t) + γ1 sin(2πt/52) + γ2 cos(2πt/52) + ε
```

Cada coeficiente es una elasticidad. En 104 semanas de datos sintéticos generados con `β1 = −1,4` y `β2 = +0,8`, el ajuste recuperó `β1 = −1,49` (IC del 95% de −1,87 a −1,11) y `β2 = +0,73` (+0,26 a +1,20). Una suba de precio del 10% reduce la demanda en 13,2%.

Con dos años de datos, el intervalo del tipo de cambio sigue siendo ancho. Y con datos reales hay un problema peor: las tiendas no cambian precios al azar. Hacen descuento cuando la demanda ya está cayendo. Eso mete la estrategia de precios dentro de `β1`. Sin pruebas de precio o un instrumento, como el costo de reposición, tómalo como una dirección, no como un número exacto.

## El quiebre de stock que todavía se puede evitar

```
cobertura (días)   = stock / demanda diaria
punto de pedido    = d̄ × L + z × σ_d × √L
```

Con 0,75 unidades por día, un desvío estándar diario de 0,9, un plazo de reposición de 10 días y 9 unidades en stock, la cobertura es de 12 días. Parece suficiente frente a un plazo de 10. El punto de pedido es de 12,2 unidades, 4,7 de ellas de stock de seguridad, para un nivel de servicio del 95%. Ya estás por debajo. El pedido tenía que salir hoy. La cobertura solo ve el promedio. El punto de pedido ve también el riesgo.

## Medir sin engañarse

**Una proporción necesita intervalo.** "El 30% de las pérdidas fue por precio", con 23 de 80 conversaciones, tiene un intervalo de [Wilson](https://doi.org/10.1080/01621459.1927.10502953) del 95% entre 20,0% y 39,5%. Con 3 de 10, va de 10,8% a 60,3%, lo que no sostiene ninguna decisión. Pon el intervalo en el reporte.

**El impacto incremental necesita un grupo de control.** La pregunta que justifica un agente de ventas es cuánto vendió que no se habría vendido de todos modos. Comparar antes y después mezcla estacionalidad, promociones y tipo de cambio. En lugar de eso, apaga el agente en un 20% de las noches, sorteadas. En el ejemplo, la conversión fuera de horario fue de 12,0% con el agente (77 de 640) y de 5,6% sin él (9 de 160): una mejora de 6,4 puntos porcentuales, IC del 95% de 2,0 a 10,8. Claramente positiva, y claramente necesitada de más semanas antes de que alguien cite una cifra exacta.

**El tiempo de respuesta es una curva, no un eslogan.** Una regresión logística sobre `ln(1 + minutos hasta la primera respuesta)` convierte "el lead se enfría" en números de esa tienda. En los datos sintéticos: 13,7% de probabilidad de compra con respuesta en 1 minuto, 8,2% a los 5, 3,7% a los 30 y 1,3% a las 4 horas. Las respuestas lentas también suelen ser conversaciones difíciles, así que solo el grupo de control da el efecto causal.

## Lo que rompe todo esto

El clasificador. Cada número de arriba hereda el error de quien etiquetó el motivo de la pérdida. Revisa 100 conversaciones a mano y mide la precisión antes de que cualquier cifra llegue al cliente.

El volumen. Una tienda mediana con unos cientos de conversaciones por mes tiene números confiables por categoría, no por SKU. El encogimiento ayuda. No crea información.

La causalidad. Las elasticidades y curvas de tiempo de respuesta observacionales son correlaciones con buenos modales. Los experimentos son los que las convierten en efectos.

La matemática es la parte fácil. Sacar un evento limpio de cada conversación es el producto de verdad.

## Referencias

- Anupindi, R., Dada, M. y Gupta, S. (1998). Estimation of consumer demand with stock-out based substitution. *Marketing Science*, 17(4), 406-423.
- Croston, J. D. (1972). Forecasting and stock control for intermittent demands. *Operational Research Quarterly*, 23(3), 289-303.
- FMI, GMA y CIES (2002). [Estudio mundial sobre las causas de los quiebres de stock en el retail](https://www.fmi.org/newsroom/news-archive/view/2002/10/14/new-industry-study-explores-root-causes-of-global-out-of-stock-dilemma).
- Hyndman, R. J. y Athanasopoulos, G. [*Forecasting: Principles and Practice*](https://otexts.com/fpp3/), 3.ª ed.
- Syntetos, A. A. y Boylan, J. E. (2005). The accuracy of intermittent demand estimates. *International Journal of Forecasting*, 21(2), 303-314.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *Journal of the American Statistical Association*, 22(158), 209-212.
