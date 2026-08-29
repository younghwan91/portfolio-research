# Factor library — 158 factors

[← README](../README.md) · [한국어](factor-library.ko.md)


Factors are not written as 158 functions. A **declarative expression DSL** generates TTM / QoQ / YoY / acceleration variants automatically.

```python
from opt_portfolio.factor.dsl.expr import F
from opt_portfolio.factor.dsl.registry import factor

# Cash-based operating profitability (Ball, Gerakos, Linnainmaa & Nikolaev 2016)
CBOP = factor(
    "CBOP",
    (F.gp - _delta(F.receivables) - _delta(F.inventory) + _delta(F.liabilitiesc)) / F.assets,
    category="quality",
    direction=1,
    neutralize=("sector",),   # cross-sectional sector neutralisation
)
```

| Category | Count | Examples |
|---|---|---|
| quality | 55 | GP/A, ROIC, F-Score, accruals, net operating assets |
| growth | 26 | Revenue / earnings YoY & QoQ |
| price | 24 | Momentum 1/3/6/12M, 12-1, low volatility |
| value_price | 24 | P/E, P/B, P/S, P/FCF, P/GP |
| acceleration | 15 | Second derivative of growth |
| value_ev | 9 | EV/EBITDA, EV/GP |
| flow_proxy | 5 | 13F institutional change, insider net buying |

Only factors with a documented rationale are included — Novy-Marx (2013), Sloan (1996), Hirshleifer et al. (2004), Daniel & Titman (2006), Ball et al. (2016), plus replications from the Chen & Zimmermann open-source asset pricing library.


Definitions live in `src/opt_portfolio/factor/library/`; the full specification is in
[`factor-system/01-factor-spec.md`](factor-system/01-factor-spec.md) (Korean).
