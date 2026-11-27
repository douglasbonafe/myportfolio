---
title: "Demanda perdida: como medir as vendas que a loja nunca fez, a partir das conversas de WhatsApp"
description: "Venda é só a demanda que a loja conseguiu atender. O resto está nas conversas de WhatsApp. Aqui está a matemática para transformar essas conversas em receita perdida, demanda real, previsões, elasticidades e alertas de ruptura, com um script que você pode rodar."
publishDate: 2026-11-27
lang: pt
key: lost-demand-whatsapp
tags:
  - Retail Analytics
  - Forecasting
  - Estatística
  - Python
cover: /assets/blog/lost-demand-whatsapp-pt.jpg
cover_alt: "Demanda perdida: 18 vendas registradas contra 22,3 unidades de demanda real, com a receita perdida por produto"
---

Na semana passada, mandei mensagem no WhatsApp de vários varejistas de eletrônicos do Paraguai, me passando por cliente. Alguns tinham um bot que não conseguia responder uma pergunta sobre estoque. Outros me empurraram para "um consultor amanhã". Alguns nunca responderam. Nenhum resolveu o meu problema.

Nada disso aparece no relatório de vendas deles. Uma venda que não aconteceu não deixa linha no ERP. Mas deixou um rastro: eu escrevi exatamente o que queria comprar, a que horas, e ninguém respondeu.

Estou construindo um agente de vendas no WhatsApp para varejistas, e o produto mais interessante acabou sendo o dado que ele coleta no caminho. Este post é a matemática por trás disso. Todos os números abaixo saem de [um script que você pode rodar](/assets/blog/lost_demand.py), com dados sintéticos e semente fixa. Nada aqui é resultado de cliente.

## Venda é demanda censurada

Quando um produto está em falta, a venda registrada vai a zero. As pessoas continuam pedindo. Em estatística, isso se chama dado censurado: você observa `min(demanda, estoque)`, nunca a demanda em si.

Se você prevê o mês seguinte com base nas vendas, subestima justamente os produtos que mais faltam. Compra menos deles. Eles faltam de novo. O erro se alimenta sozinho.

O efeito não é pequeno. O estudo mundial sobre ruptura feito em 2002 para [FMI, GMA e CIES](https://www.fmi.org/newsroom/news-archive/view/2002/10/14/new-industry-study-explores-root-causes-of-global-out-of-stock-dilemma) encontrou uma taxa média de ruptura de 8,3%. Diante dela, 31% dos clientes vão a outra loja, 26% trocam de marca e 9% não compram nada.

Uma loja física não enxerga nada disso, porque o cliente vai embora sem dizer nada. Num canal de conversa é diferente. O cliente escreve o que queria.

## Passo zero: cada conversa vira um evento

Nenhuma fórmula funciona em cima de texto solto. O agente, ou um classificador ao lado dele, precisa transformar cada conversa num registro:

| Campo | Exemplo |
|---|---|
| `first_msg_ts`, `first_reply_ts` | 2026-11-20 22:14, 2026-11-21 09:02 |
| `product_id`, `quantity`, `offered_price` | SKU do ERP, 1, US$ 820 |
| `in_stock` | não |
| `outcome` | venda, desistência, sem resposta |
| `loss_reason` | ruptura, preço, demora, fora do catálogo, concorrente |
| `handled_by` | agente, humano, ninguém |

Dois detalhes pesam mais do que parecem. A unidade de análise é o par conversa e produto, porque uma conversa pode ser sobre três produtos. E só entram no denominador da conversão as conversas com intenção de compra. Uma dúvida sobre garantia contada como venda perdida derruba todas as taxas.

## Receita perdida, do jeito certo

A versão tentadora é "somar o preço de tudo que não vendemos". Está errada, porque nem todo mundo que pergunta compraria, mesmo com estoque e resposta na hora. Multiplique pela chance real de venda:

```
R_p = N_p × ĉ_p × q̄_p × P_p

N_p   conversas do produto p perdidas por ruptura, demora ou fora do catálogo
ĉ_p   taxa de conversão de p quando havia estoque e alguém respondeu
q̄_p   unidades médias por venda
P_p   preço
```

Perdas por preço ficam fora dessa soma. Ali a loja fez a parte dela e o cliente disse não. Isso é uma questão de elasticidade, mais abaixo.

### Não confie numa taxa feita com seis conversas

Um produto com 6 conversas atendidas e 2 vendas converte 33%. Isso é ruído. Encolha a taxa de cada produto em direção à categoria, com uma priori Beta:

```
ĉ_p = (vendas_p + α × c_categoria) / (atendidas_p + α)
```

`α` é quantas conversas a categoria vale. Com `α = 20`, um produto precisa de umas 20 conversas próprias antes que a taxa dele domine.

Smartphones convertendo 14%, um mês:

| Produto | Atendidas | Vendas | Taxa bruta | Taxa encolhida | Conversas perdidas | Receita perdida |
|---|---|---|---|---|---|---|
| Phone A 128GB, US$ 820 | 100 | 18 | 18,0% | 17,3% | 40 | US$ 5.685 |
| Phone B 256GB, US$ 1.150 | 6 | 2 | 33,3% | 18,5% | 4 | US$ 849 |
| Carregador 30W, US$ 25, 1,4 un./venda | 60 | 21 | 35,0% | 29,8% | 13 | US$ 135 |

Total: US$ 6.670. Com a taxa bruta, a perda do Phone B sairia 80% maior, com base em seis conversas.

## Demanda real: devolva o que a ruptura escondeu

```
D = vendas observadas + N_ruptura × ĉ × q̄
```

O Phone A vendeu 18 unidades e perdeu 25 conversas por ruptura. A 17,3%, são 4,33 unidades escondidas. Demanda real: 22,3 unidades, 24% acima do que as vendas dizem. É esse o número que o próximo pedido de compra deve usar.

Sem dado de conversa, o atalho clássico é `vendas / fração dos dias com estoque`. Com 22 de 30 dias em estoque, ele dá 24,5 unidades. A diferença vem da hipótese escondida de que a procura nos dias de ruptura é igual à dos dias normais. A conversa não supõe nada. Ela viu a demanda acontecer.

## Previsão: escolha o método pelo jeito que o produto vende

Preveja sobre a demanda real, nunca sobre as vendas. Depois:

- Poucas semanas de histórico, sem tendência: suavização exponencial simples, `ŷ(t+1) = ŷ(t) + a × (y(t) − ŷ(t))`.
- Tendência e sazonalidade: Holt-Winters. Para sazonalidade anual em dados semanais, você precisa de dois anos de histórico, senão confunde um ano bom com efeito de Black Friday.
- Produtos de giro lento, que são a maior parte de um catálogo de eletrônicos: Croston (1972) ou, melhor, SBA.

O Croston mantém duas séries suavizadas, atualizadas só quando há venda: o tamanho da venda `z` e o intervalo entre vendas `p`. A previsão é `z / p`. Syntetos e Boylan (2005) mostraram que ela é viesada para cima e multiplicaram por `(1 − a/2)`. Isso é o SBA.

Num produto sintético de giro lento que vende em 35% das semanas (demanda real de 0,875 unidade por semana), treinado em 78 semanas e testado nas 26 seguintes:

| Método | Previsão por semana | Viés no período de teste | WAPE |
|---|---|---|---|
| Suavização simples | 1,202 | +48,8% | 1,50 |
| Croston | 1,010 | +25,1% | 1,39 |
| SBA | 0,909 | +12,6% | 1,35 |

WAPE acima de 1 parece erro, mas não é: uma previsão constante erra toda semana de zero. Em demanda intermitente, quem decide é o viés, porque viés vira estoque parado ou ruptura. O do SBA é quase quatro vezes menor.

E a regra que vale para todos: nenhuma previsão vai para o cliente sem backtest.

## Elasticidade: preço e o real

Lojas de fronteira no Paraguai vendem para brasileiros, então o câmbio mexe na demanda tanto quanto o preço. Uma regressão log-log com termos de Fourier para a sazonalidade:

```
ln D(t) = β0 + β1 ln P(t) + β2 ln E(t) + γ1 sin(2πt/52) + γ2 cos(2πt/52) + ε
```

Cada coeficiente é uma elasticidade. Em 104 semanas de dados sintéticos gerados com `β1 = −1,4` e `β2 = +0,8`, o ajuste recuperou `β1 = −1,49` (IC de 95% de −1,87 a −1,11) e `β2 = +0,73` (+0,26 a +1,20). Um aumento de 10% no preço reduz a demanda em 13,2%.

Dois anos de dado e o intervalo do câmbio ainda é largo. E com dado real há um problema pior: loja não muda preço ao acaso. Ela dá desconto quando a procura já está caindo. Isso vaza a estratégia de preço para dentro do `β1`. Sem testes de preço ou um instrumento, como o custo de reposição, trate o número como direção, não como valor exato.

## A ruptura que ainda dá para evitar

```
cobertura (dias)  = estoque / demanda diária
ponto de pedido   = d̄ × L + z × σ_d × √L
```

Com 0,75 unidade por dia, desvio-padrão diário de 0,9, prazo de reposição de 10 dias e 9 unidades em estoque, a cobertura é de 12 dias. Parece tranquilo diante de um prazo de 10. O ponto de pedido é de 12,2 unidades, 4,7 delas de estoque de segurança, para um nível de serviço de 95%. Você já está abaixo dele. O pedido devia ter saído hoje. A cobertura só enxerga a média. O ponto de pedido enxerga o risco também.

## Medir sem se enganar

**Proporção precisa de intervalo.** "30% das perdas foram por preço", com 23 de 80 conversas, tem intervalo de [Wilson](https://doi.org/10.1080/01621459.1927.10502953) de 95% entre 20,0% e 39,5%. Com 3 de 10, vai de 10,8% a 60,3%, o que não sustenta decisão nenhuma. Coloque o intervalo no relatório.

**Ganho incremental precisa de grupo de controle.** A pergunta que justifica um agente de vendas é quanto ele vendeu que não teria sido vendido de qualquer jeito. Comparar antes e depois mistura sazonalidade, promoção e câmbio. Em vez disso, desligue o agente em 20% das noites, sorteadas. No exemplo, a conversão fora do horário foi de 12,0% com o agente (77 de 640) e de 5,6% sem ele (9 de 160): um ganho de 6,4 pontos percentuais, IC de 95% de 2,0 a 10,8. Claramente positivo, e claramente precisando de mais semanas antes que alguém cite um número exato.

**Tempo de resposta é uma curva, não um slogan.** Uma regressão logística sobre `ln(1 + minutos até a primeira resposta)` transforma "o lead esfria" em números daquela loja. Nos dados sintéticos: 13,7% de chance de compra com resposta em 1 minuto, 8,2% em 5, 3,7% em 30 e 1,3% em 4 horas. Respostas lentas também tendem a ser conversas difíceis, então só o grupo de controle dá o efeito causal.

## O que derruba tudo isso

O classificador. Todo número acima herda o erro de quem rotulou o motivo da perda. Confira 100 conversas à mão e meça a precisão antes de qualquer número chegar ao cliente.

O volume. Um varejista médio com algumas centenas de conversas por mês tem números confiáveis por categoria, não por SKU. O encolhimento ajuda. Ele não cria informação.

A causalidade. Elasticidades e curvas de tempo de resposta observacionais são correlações bem-educadas. São os experimentos que transformam isso em efeito.

A matemática é a parte fácil. Tirar um evento limpo de cada conversa é o produto de verdade.

## Referências

- Anupindi, R., Dada, M. e Gupta, S. (1998). Estimation of consumer demand with stock-out based substitution. *Marketing Science*, 17(4), 406-423.
- Croston, J. D. (1972). Forecasting and stock control for intermittent demands. *Operational Research Quarterly*, 23(3), 289-303.
- FMI, GMA e CIES (2002). [Estudo mundial sobre as causas da ruptura no varejo](https://www.fmi.org/newsroom/news-archive/view/2002/10/14/new-industry-study-explores-root-causes-of-global-out-of-stock-dilemma).
- Hyndman, R. J. e Athanasopoulos, G. [*Forecasting: Principles and Practice*](https://otexts.com/fpp3/), 3ª ed.
- Syntetos, A. A. e Boylan, J. E. (2005). The accuracy of intermittent demand estimates. *International Journal of Forecasting*, 21(2), 303-314.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *Journal of the American Statistical Association*, 22(158), 209-212.
