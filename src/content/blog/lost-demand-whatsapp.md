---
title: "Lost Demand: Measuring the Sales a Store Never Made, From WhatsApp Conversations"
description: "Sales are only the demand a store managed to serve. The rest is sitting in WhatsApp chats. Here is the math to turn those chats into lost revenue, true demand, forecasts, elasticities and stockout alerts, with a script you can run."
publishDate: 2026-11-27
lang: en
key: lost-demand-whatsapp
tags:
  - Retail Analytics
  - Forecasting
  - Statistics
  - Python
cover: /assets/blog/lost-demand-whatsapp.jpg
cover_alt: "Lost Demand: 18 recorded sales versus 22.3 units of true demand, with lost revenue per product"
---

Last week I messaged several electronics retailers in Paraguay on WhatsApp, posing as a customer. Some had a bot that couldn't answer a stock question. Some pushed me to "a sales advisor tomorrow". A few never replied at all. Not one of them solved my problem.

None of that shows up in their sales reports. A sale that didn't happen leaves no row in the ERP. But it did leave a trace: I wrote down exactly what I wanted to buy, at what time, and nobody answered.

I'm building a WhatsApp sales agent for retailers, and the more interesting product turned out to be the data it collects on the side. This post is the math behind it. Every number below comes from [a script you can run](/assets/blog/lost_demand.py), on synthetic data with a fixed seed. Nothing here is a client result.

## Sales are censored demand

When a product is out of stock, recorded sales drop to zero. People keep asking for it. Statisticians call this censored data: you observe `min(demand, stock)`, never demand itself.

If you forecast next month from sales, you underestimate exactly the products that run out most often. You buy fewer of them. They run out again. The error feeds itself.

It isn't a small effect. The 2002 worldwide out-of-stock study for [FMI, GMA and CIES](https://www.fmi.org/newsroom/news-archive/view/2002/10/14/new-industry-study-explores-root-causes-of-global-out-of-stock-dilemma) found an average stockout rate of 8.3%. Facing one, 31% of shoppers go to another store, 26% switch brands and 9% buy nothing.

A physical store can't see any of that, because the shopper leaves without a word. A chat channel is different. The customer types what they wanted.

## Step zero: every conversation becomes an event

No formula works on loose text. The agent, or a classifier next to it, has to turn each conversation into a record:

| Field | Example |
|---|---|
| `first_msg_ts`, `first_reply_ts` | 2026-11-20 22:14, 2026-11-21 09:02 |
| `product_id`, `quantity`, `offered_price` | ERP SKU, 1, US$ 820 |
| `in_stock` | no |
| `outcome` | sale, dropped, no reply |
| `loss_reason` | stockout, price, delay, not stocked, competitor |
| `handled_by` | agent, human, nobody |

Two details matter more than they look. The unit of analysis is the conversation-product pair, because one chat can be about three products. And only conversations with purchase intent go into a conversion denominator. A warranty question counted as a lost sale drags every rate down.

## Lost revenue, done properly

The tempting version is "sum the price of everything we didn't sell". It's wrong, because not everyone who asks would buy, even with stock and an instant reply. Multiply by the real chance of a sale:

```
R_p = N_p × ĉ_p × q̄_p × P_p

N_p   conversations for product p lost to stockout, delay or not stocked
ĉ_p   conversion rate for p when it was in stock and someone replied
q̄_p   average units per sale
P_p   price
```

Losses on price stay out of this sum. There the store did its job and the customer said no. That's an elasticity question, further down.

### Don't trust a rate built on six conversations

A product with 6 served chats and 2 sales converts at 33%. That's noise. Shrink each product's rate toward its category with a Beta prior:

```
ĉ_p = (sales_p + α × c_category) / (served_p + α)
```

`α` is how many conversations the category is worth. With `α = 20`, a product needs about 20 chats of its own before its own rate dominates.

Smartphones converting at 14%, one month:

| Product | Served | Sales | Raw rate | Shrunk rate | Lost chats | Lost revenue |
|---|---|---|---|---|---|---|
| Phone A 128GB, US$ 820 | 100 | 18 | 18.0% | 17.3% | 40 | US$ 5,685 |
| Phone B 256GB, US$ 1,150 | 6 | 2 | 33.3% | 18.5% | 4 | US$ 849 |
| Charger 30W, US$ 25, 1.4 units/sale | 60 | 21 | 35.0% | 29.8% | 13 | US$ 135 |

Total: US$ 6,670. With the raw rate, Phone B's loss would have come out 80% higher, on the strength of six chats.

## True demand: add back what the stockout hid

```
D = observed sales + N_stockout × ĉ × q̄
```

Phone A sold 18 units and lost 25 chats to stockouts. At 17.3%, that's 4.33 hidden units. True demand: 22.3 units, 24% above what sales say. That's the number the next purchase order should use.

Without chat data, the classic shortcut is `sales / share of days in stock`. With 22 of 30 days in stock it gives 24.5 units. The difference comes from its hidden assumption that demand on stockout days equals demand on normal days. The conversation doesn't assume. It saw the demand happen.

## Forecasting: pick the method by how the product sells

Forecast on true demand, never on sales. Then:

- A few weeks of history, no trend: simple exponential smoothing, `ŷ(t+1) = ŷ(t) + a × (y(t) − ŷ(t))`.
- Trend and seasonality: Holt-Winters. For yearly seasonality on weekly data you want two years of history, or you'll mistake a good year for a Black Friday effect.
- Slow movers, which is most of an electronics catalogue: Croston (1972), or better, SBA.

Croston keeps two smoothed series, updated only when a sale happens: the size of a sale `z` and the gap between sales `p`. The forecast is `z / p`. Syntetos and Boylan (2005) showed it's biased upward and multiplied it by `(1 − a/2)`. That's SBA.

On a synthetic slow mover that sells in 35% of weeks (true demand 0.875 units a week), trained on 78 weeks and tested on the next 26:

| Method | Forecast per week | Bias over the test period | WAPE |
|---|---|---|---|
| Simple smoothing | 1.202 | +48.8% | 1.50 |
| Croston | 1.010 | +25.1% | 1.39 |
| SBA | 0.909 | +12.6% | 1.35 |

WAPE above 1 looks broken but isn't: a flat forecast misses every zero week. For intermittent demand, bias is the metric that decides, because bias becomes dead stock or stockouts. SBA's is almost four times smaller.

And the rule that applies to all of them: no forecast goes to a client without a backtest.

## Elasticity: price, and the Brazilian real

Border stores in Paraguay sell to Brazilians, so the exchange rate moves demand as much as price does. A log-log regression with Fourier terms for seasonality:

```
ln D(t) = β0 + β1 ln P(t) + β2 ln E(t) + γ1 sin(2πt/52) + γ2 cos(2πt/52) + ε
```

Each coefficient is an elasticity. On 104 weeks of synthetic data generated with `β1 = −1.4` and `β2 = +0.8`, the fit recovered `β1 = −1.49` (95% CI −1.87 to −1.11) and `β2 = +0.73` (+0.26 to +1.20). A 10% price increase cuts demand by 13.2%.

Two years of data and the exchange-rate interval is still wide. And with real data there's a worse problem: stores don't move prices at random. They discount when demand is already falling. That leaks the pricing strategy into `β1`. Without price tests or an instrument such as replacement cost, treat it as a direction, not a number.

## The stockout you can still prevent

```
cover (days)   = stock / daily demand
reorder point  = d̄ × L + z × σ_d × √L
```

With 0.75 units a day, a daily standard deviation of 0.9, a 10-day lead time and 9 units on hand, cover is 12 days. Looks fine against a 10-day lead time. The reorder point is 12.2 units, 4.7 of them safety stock at a 95% service level. You're already below it. The order should have gone out today. Cover only sees the average. The reorder point sees the risk too.

## Measuring without fooling yourself

**Proportions need intervals.** "30% of losses were about price" from 23 of 80 chats has a [Wilson](https://doi.org/10.1080/01621459.1927.10502953) 95% interval of 20.0% to 39.5%. From 3 of 10 it runs from 10.8% to 60.3%, which supports no decision at all. Put the interval in the report.

**Incrementality needs a control group.** The question that justifies a sales agent is how much it sold that wouldn't have sold anyway. Before-and-after mixes in seasonality, promotions and the exchange rate. Switch the agent off on a random 20% of nights instead. In the example, after-hours conversion was 12.0% with the agent (77 of 640) and 5.6% without (9 of 160): a lift of 6.4 percentage points, 95% CI 2.0 to 10.8. Clearly positive, and clearly in need of more weeks before anyone quotes an exact figure.

**Response time is a curve, not a slogan.** A logistic regression on `ln(1 + minutes to first reply)` turns "leads go cold" into numbers for that store. On the synthetic data: 13.7% purchase probability with a reply in 1 minute, 8.2% at 5, 3.7% at 30, 1.3% at 4 hours. Slow replies also tend to be hard conversations, so only the control group gives you the causal effect.

## What breaks all of this

The classifier. Every number above inherits the error of whatever labelled the loss reason. Hand-check 100 conversations and measure precision before any figure reaches a client.

Volume. A mid-sized retailer with a few hundred chats a month gets reliable numbers per category, not per SKU. Shrinkage helps. It doesn't create information.

Causality. Observational elasticities and response-time curves are correlations with good manners. Experiments are what make them effects.

The math is the easy part. Getting a clean event out of every conversation is the actual product.

## References

- Anupindi, R., Dada, M. and Gupta, S. (1998). Estimation of consumer demand with stock-out based substitution. *Marketing Science*, 17(4), 406-423.
- Croston, J. D. (1972). Forecasting and stock control for intermittent demands. *Operational Research Quarterly*, 23(3), 289-303.
- FMI, GMA and CIES (2002). [Worldwide study on the root causes of retail out-of-stocks](https://www.fmi.org/newsroom/news-archive/view/2002/10/14/new-industry-study-explores-root-causes-of-global-out-of-stock-dilemma).
- Hyndman, R. J. and Athanasopoulos, G. [*Forecasting: Principles and Practice*](https://otexts.com/fpp3/), 3rd ed.
- Syntetos, A. A. and Boylan, J. E. (2005). The accuracy of intermittent demand estimates. *International Journal of Forecasting*, 21(2), 303-314.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *Journal of the American Statistical Association*, 22(158), 209-212.
