"""Worked example for "Lost demand from WhatsApp conversations".

Every number in the article comes from this script. All data is synthetic
and seeded, so the results are reproducible. Requires only numpy.
"""
import math
import numpy as np

rng = np.random.default_rng(42)


# ---------------------------------------------------------------------------
# 1. Lost revenue with a shrunk conversion rate
# ---------------------------------------------------------------------------
# For each product: conversations that were answered with stock ("served"),
# sales among them, conversations lost to stockout / no reply / not stocked,
# average units per sale and price in USD.
CATEGORY_CONVERSION = 0.14   # smartphones, all products pooled
ALPHA = 20                   # prior weight, in conversations

products = {
    #               served sales lost_stockout lost_noreply q    price
    "Phone A 128GB": (100, 18, 25, 15, 1.0, 820.0),
    "Phone B 256GB": (6, 2, 3, 1, 1.0, 1150.0),
    "Charger 30W":   (60, 21, 4, 9, 1.4, 25.0),
}


def shrunk_rate(sales, served, prior=CATEGORY_CONVERSION, alpha=ALPHA):
    return (sales + alpha * prior) / (served + alpha)


print("1. Lost revenue")
total_lost = 0.0
for name, (served, sales, lost_so, lost_nr, q, price) in products.items():
    raw = sales / served
    c = shrunk_rate(sales, served)
    lost_conv = lost_so + lost_nr
    lost_rev = lost_conv * c * q * price
    total_lost += lost_rev
    print(f"   {name:14s} raw={raw:.3f} shrunk={c:.4f} lost_conv={lost_conv:3d} "
          f"lost_revenue=${lost_rev:,.0f}")
print(f"   total lost revenue: ${total_lost:,.0f}\n")


# ---------------------------------------------------------------------------
# 2. Unconstrained demand: sales plus what the stockout hid
# ---------------------------------------------------------------------------
served, sales, lost_so, _, q, _ = products["Phone A 128GB"]
c = shrunk_rate(sales, served)
hidden_units = lost_so * c * q
unconstrained = sales * q + hidden_units
print("2. Unconstrained demand (Phone A, one month)")
print(f"   observed sales: {sales*q:.1f} units, hidden by stockout: {hidden_units:.2f}, "
      f"true demand: {unconstrained:.2f} (+{hidden_units/(sales*q):.0%})")
# Naive proxy: sales / share of days in stock (22 of 30 days)
days_in_stock = 22
print(f"   naive proxy sales/(22/30): {sales*q/(days_in_stock/30):.2f} units\n")


# ---------------------------------------------------------------------------
# 3. Forecasting intermittent demand: SES vs Croston vs SBA
# ---------------------------------------------------------------------------
def ses(y, a=0.2):
    f = np.empty(len(y) + 1)
    f[0] = y[0]
    for t, v in enumerate(y):
        f[t + 1] = f[t] + a * (v - f[t])
    return f  # f[t] is the forecast made for period t


def croston(y, a=0.2, sba=False):
    f = np.full(len(y) + 1, np.nan)
    first = np.flatnonzero(y)[0]
    z, p, k = y[first], first + 1.0, 1
    for t in range(len(y)):
        if t > first:
            if y[t] > 0:
                z = z + a * (y[t] - z)
                p = p + a * (k - p)
                k = 1
            else:
                k += 1
        factor = (1 - a / 2) if sba else 1.0
        f[t + 1] = factor * z / p
    return f


def wape(actual, forecast):
    return np.abs(actual - forecast).sum() / actual.sum()


# 104 weeks of a slow mover: sells in ~35% of weeks, 1 to 4 units when it does
weeks = 104
occurs = rng.random(weeks) < 0.35
size = rng.integers(1, 5, weeks)
y = np.where(occurs, size, 0).astype(float)
train, test = y[:78], y[78:]

print("3. Intermittent demand, backtest on the last 26 weeks")
print(f"   true mean demand per week: {0.35*2.5:.3f}, test mean: {test.mean():.3f}")
for label, fc in [("SES", ses(train)), ("Croston", croston(train)),
                  ("SBA", croston(train, sba=True))]:
    level = fc[-1]                       # flat forecast for the next 26 weeks
    err = wape(test, np.full_like(test, level))
    bias = (level * len(test) - test.sum()) / test.sum()
    print(f"   {label:8s} forecast/week={level:.3f} WAPE={err:.2f} bias={bias:+.1%}")
print()


# ---------------------------------------------------------------------------
# 4. Price and exchange-rate elasticity: log-log regression
# ---------------------------------------------------------------------------
# Weekly demand for a border store. True elasticities: price -1.4, BRL/PYG +0.8
n = 104
t = np.arange(n)
price = 800 * np.exp(rng.normal(0, 0.06, n))
brl_pyg = 1450 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
season = 0.25 * np.sin(2 * np.pi * t / 52)
log_d = 3.2 - 1.4 * np.log(price / 800) + 0.8 * np.log(brl_pyg / 1450) + season \
        + rng.normal(0, 0.12, n)

X = np.column_stack([np.ones(n), np.log(price), np.log(brl_pyg),
                     np.sin(2 * np.pi * t / 52), np.cos(2 * np.pi * t / 52)])
beta, *_ = np.linalg.lstsq(X, log_d, rcond=None)
resid = log_d - X @ beta
sigma2 = resid @ resid / (n - X.shape[1])
se = np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X)))
print("4. Elasticities (true: price -1.4, BRL/PYG +0.8)")
print(f"   price:   {beta[1]:+.2f}  (95% CI {beta[1]-1.96*se[1]:+.2f} to {beta[1]+1.96*se[1]:+.2f})")
print(f"   BRL/PYG: {beta[2]:+.2f}  (95% CI {beta[2]-1.96*se[2]:+.2f} to {beta[2]+1.96*se[2]:+.2f})")
print(f"   a 10% price rise moves demand by {(1.10**beta[1]-1):+.1%}\n")


# ---------------------------------------------------------------------------
# 5. Days of cover and reorder point
# ---------------------------------------------------------------------------
d_mean, d_sd, lead, z, stock = 0.75, 0.9, 10, 1.65, 9
rop = d_mean * lead + z * d_sd * math.sqrt(lead)
print("5. Stockout warning")
print(f"   days of cover: {stock/d_mean:.1f}, reorder point: {rop:.1f} units "
      f"(safety stock {z*d_sd*math.sqrt(lead):.1f})")
print(f"   stock {stock} < ROP {rop:.1f}: reorder now\n")


# ---------------------------------------------------------------------------
# 6. Wilson interval for an objection share
# ---------------------------------------------------------------------------
def wilson(k, n, z=1.96):
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, centre - half, centre + half


print("6. Share of lost conversations that cited price")
for k, n_ in [(23, 80), (3, 10)]:
    p, lo, hi = wilson(k, n_)
    print(f"   {k}/{n_}: {p:.1%}, 95% Wilson interval {lo:.1%} to {hi:.1%}")
print()


# ---------------------------------------------------------------------------
# 7. Incremental revenue with a holdout
# ---------------------------------------------------------------------------
# Off-hours conversations. Agent on for most nights, off on a random 20%.
n_on, s_on = 640, 77     # agent answered
n_off, s_off = 160, 9    # agent off (holdout), human replies next morning
p_on, p_off = s_on / n_on, s_off / n_off
diff = p_on - p_off
se_diff = math.sqrt(p_on * (1 - p_on) / n_on + p_off * (1 - p_off) / n_off)
ticket = 310.0
print("7. Holdout test, off-hours conversion")
print(f"   agent on {p_on:.1%}, agent off {p_off:.1%}, lift {diff*100:+.1f} pp "
      f"(95% CI {(diff-1.96*se_diff)*100:+.1f} to {(diff+1.96*se_diff)*100:+.1f} pp)")
print(f"   incremental sales: {diff*n_on:.0f}, incremental revenue: ${diff*n_on*ticket:,.0f}\n")


# ---------------------------------------------------------------------------
# 8. Response time vs conversion: logistic regression by Newton's method
# ---------------------------------------------------------------------------
m = 1500
minutes = rng.exponential(45, m).clip(0.5, 600)
logit_true = -1.2 - 0.6 * np.log1p(minutes)
bought = rng.random(m) < 1 / (1 + np.exp(-logit_true))
Xl = np.column_stack([np.ones(m), np.log1p(minutes)])
w = np.zeros(2)
for _ in range(25):
    p = 1 / (1 + np.exp(-Xl @ w))
    grad = Xl.T @ (bought - p)
    hess = Xl.T @ (Xl * (p * (1 - p))[:, None])
    w += np.linalg.solve(hess, grad)
print("8. Response time vs conversion (true slope -0.60 on log(1+min))")
print(f"   fitted: intercept {w[0]:+.2f}, slope {w[1]:+.2f}")
for mins in (1, 5, 30, 240):
    pr = 1 / (1 + np.exp(-(w[0] + w[1] * math.log1p(mins))))
    print(f"   reply in {mins:>3d} min: P(buy) = {pr:.1%}")
