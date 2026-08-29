# portfolio-research

**English** · [한국어](README.ko.md)

**US equity factor engine + tactical asset allocation (TAA) validation system.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-younghwan--chae-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/younghwan-chae/)

Three subsystems live in this repository.

| | **Factor engine** (`factor/`) | **TAA allocation** (`taa/`) | **Original VAA** (`strategies/`) |
|---|---|---|---|
| Scope | US single stocks (20,931 tickers, 1997–2026) | 18 ETFs | 7–11 ETFs |
| Question | Which stocks to buy | Which asset class to rotate into | (same — first attempt) |
| Data | Sharadar direct (point-in-time, delisted included) | Sharadar funds bulk (`closeadj`) | yfinance daily closes |
| Entry point | `opt-factor` · `opt-factor-tui` | `scripts/run_taa.py` | `make run` · `run.py` |
| Outcome | **1 adopted** (large-cap) | **0 adopted** — all 9 failed the PBO gate | Kept as the record of why it failed |

**None of the three imports another**, with one exception: `taa/` →
`factor.research.overfitting` (DSR and PBO). Not trusting performance produced without
a gate is this repository's standing rule.

---

# 1. Factor engine

A cross-sectional US equity factor engine built so that results can be **trusted, not just produced**.
One design principle drives everything: **never fail silently.**

## Why this engine

Quant backtests fail in a small number of well-known ways. Each one is blocked structurally here.

| Common failure | How it is prevented |
|---|---|
| **Survivorship bias** — only today's survivors are in the sample | Delisted names retained (Enron, old American Airlines, Ambac verified present) |
| **Look-ahead** — using numbers before they were public | Expressions cannot touch raw tables; everything passes through `PanelContext`, which enforces `datekey` alignment |
| **Restatement contamination** — using revised figures | **First print wins** — only the number the market originally saw is stored |
| **Silent truncation** — partial data reported as success | Pagination raises `TruncatedDataError` when the expected range isn't reached |
| **Overfitting** — run hundreds of variants, report the best | **Deflated Sharpe Ratio** + **PBO** charge for the number of trials |
| **In-sample performance reporting** | Official performance is **walk-forward only**; single backtests are labelled reference-only |

## Performance

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/performance-dark.png">
  <img alt="Cumulative growth over the walk-forward validation window, 2002-12 to 2026-08: large-cap 5-factor with 200-day timing reaches 36x at 15bps slippage and 27x at 50bps, against 14x for SPY buy-and-hold. Log vertical axis." src="docs/images/performance-light.png">
</picture>

*Log scale — equal slopes mean equal returns. The flat stretches in 2008, 2012 and
2022 are the 200-day overlay holding cash; those three are where the drawdown
parts company with SPY. (Chart labels are Korean; the alt text carries the reading.)*

<!-- PERFORMANCE:START -->

*Operating candidate · walk-forward validation window · 2002-12 – 2026-08 (23.6y)*

**Large-cap, 5 factors + 200-day moving-average timing overlay** (`configs/strategy_lean_timed.json`)

| Metric | Slippage 15bps | Slippage 50bps | SPY (same window) |
|---|---|---|---|
| CAGR | **16.34%** | 14.91% | 11.66% |
| Max drawdown | −24.3% | −24.3% | −55.2% |
| Volatility | 15.7% | 15.7% | 18.6% |
| Sharpe | **0.727** | 0.648 | 0.418 |
| Calmar | **0.67** | 0.61 | 0.21 |
| Deflated Sharpe (72 parameter trials) | **0.996** ✓ | 0.988 ✓ | — |
| Deflated Sharpe (**35 strategy trials**) | **0.982** ✓ | 0.957 ✓ | — |
| PBO (CSCV over 35 configs · monthly · S=16) | **0.303** ✓ | — | — |

**This strategy is measured with the guards switched on** — $5 minimum price, $1M
minimum dollar volume, and slippage. The universe is the historical S&P 500, so
there is **no capacity limit**. Raising slippage to 50bps leaves drawdown and
volatility unchanged and costs 1.4pp of return.

The last two rows charge for the search **outside** the walk-forward — "35 strategies
were tried and one was picked". The reasoning behind the gate's settings (monthly,
S=16) is below. Reproduce with `uv run python scripts/strategy_search_cost.py`; it
reads only `results/oos/` and needs no vendor data.

<!-- PERFORMANCE:END -->

## What was retired, and what it cost

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/guards-dark.png">
  <img alt="Cumulative growth of the micro-cap strategy: 153x with the guards off, 0.040x with them on — a 96% loss of principal. Log vertical axis." src="docs/images/guards-light.png">
</picture>

*Same strategy, same window; the only difference is slippage, minimum price and
minimum dollar volume. The blue line was this README's headline until 2026-08-16.*

A **micro-cap, 8-factor strategy** at CAGR 23.78% stood here until the three guards
the design document calls mandatory were switched on. They collapse it — **Sharpe
1.047 → −0.224** — because 98% of the universe disappears with them on. The headline
moved to the large-cap strategy, which had always been measured with its guards on and
so had never been compared on equal terms.

Over twenty candidates were rejected at the Deflated Sharpe gate, the PBO number was
published wrong twice before it was measured properly, and nine allocation
configurations were pre-registered and all nine rejected. **The whole trail is written
down:** [`docs/journal/`](docs/journal/README.md).

## Factor library — 158 factors

Not 158 functions — a **declarative expression DSL** generates TTM / QoQ / YoY /
acceleration variants automatically, and only factors with a documented rationale are
included (Novy-Marx 2013, Sloan 1996, Ball et al. 2016, plus Chen & Zimmermann
replications). Categories and counts: [`docs/factor-library.md`](docs/factor-library.md).

## Usage

> **Every number here was measured on data through 2026-08-14**, and the outputs in
> [`results/`](results/) are what ships — so the reported performance **can be checked
> without vendor data.** Re-running it needs a [Sharadar](https://sharadar.com)
> subscription, the only retail-priced source with point-in-time fundamentals *and*
> delisted coverage. The adapter sits behind a neutral `Provider` protocol, so
> swapping sources means rewriting one file.

```bash
# Ingest data (Sharadar subscription required)
export SHARADAR_API_KEY=...
opt-factor ingest --store us.duckdb --provider sharadar \
  --tables sf1,sep,daily,actions,sp500,tickers

# Screen factor predictive power — decile spread, IC, turnover
uv run python scripts/factor_lab.py --store us.duckdb --factors GP_A,PER,SIZE

# Official performance (walk-forward + Deflated Sharpe)
opt-factor optimize --store us.duckdb --config configs/strategy_lean_timed.json \
  --space configs/space.json --objective calmar

# What to buy today (pass current holdings to get a trade plan)
opt-factor holdings --store us.duckdb \
  --config configs/strategy_lean_timed.json --current my_holdings.csv
```

A strategy is fully declared by one JSON file in [`configs/`](configs/README.md) —
adopted, rejected and retired alike, including the operating parameters.

---

# 2. Tactical asset allocation (TAA)

Rotating between 18 ETFs monthly rather than picking single stocks. **Nine
configurations were pre-registered and all nine were rejected: PBO = 0.770.** The gate
was not relaxed.

That does not mean nothing works. All six BAA variants (Keller 2022) beat 60/40 on
Calmar without exception, 0.535–0.812 against 0.354 — but PBO across just those six is
0.861, so **which one is best cannot be determined from this data.** Both sentences
have to stand together.

The nine configurations, the eight defects caught along the way, and why VAA measured
6.07% here against the papers' 16–17% are in
[`docs/taa/01-results.md`](docs/taa/01-results.md) (Korean) and
[`docs/journal/`](docs/journal/README.md).

```bash
uv run python scripts/run_taa.py    # 9 configurations · PBO · verdict table
make run                            # original VAA (yfinance, kept for the record)
```

---

## Install & develop

```bash
make install        # uv sync --extra dev
make test           # pytest + coverage (403 tests)
make lint           # ruff check + format --check
make typecheck      # mypy src/
```

Dependencies are managed with **uv** (`uv.lock`). Do not use `pip install`. Code lives
in `src/opt_portfolio/`: `factor/`, `taa/`, `strategies/`, with `analysis/` and
`core/` shared.

Design documents are Korean, in [`docs/factor-system/`](docs/factor-system/) — specs,
the **data contract** (store schema · PIT rules · vendor measurements), the
walk-forward mathematics, and the **experiment log** with the full rejection list. In
English: [`docs/journal/`](docs/journal/README.md) and
[`docs/factor-library.md`](docs/factor-library.md).

## Limitations

- **The window contains only three major drawdowns** (2008, 2020, 2022). A strategy
  whose claim is drawdown defence rests that claim on three events. This is the
  largest remaining limitation.
- **Transaction costs are an assumption, not a measurement.** 15bps and 50bps are both
  reported and the conclusion holds at either, but the realised spread of the actual
  holdings was never measured.
- **The factor set itself is not charged.** 124 factors were screened to reach the five
  in use, and no trial count pays for that search. The outer search over 35 strategies
  *is* charged (PBO 0.303 · DSR 0.982).
- **Numbers stop at 2026-08-14** and nothing has been re-measured on newer bulk. The
  Sharadar subscription ended, so `ingest` now fails by design. Taxes are not modelled.
- TAA adopted nothing, so it has no operating conclusion. The original VAA in
  `strategies/` is in-sample on a different data source — for comparison use `taa/`.

> ⚠️ All backtests are historical and do not guarantee future returns.

## License

MIT

---
## ⭐ If this helped

If you found this useful, please **[⭐ Star](https://github.com/younghwan91/portfolio-research)** the repository — it improves discoverability for others looking for the same thing.

- 🐛 Bugs & questions → [Issues](https://github.com/younghwan91/portfolio-research/issues)
- 📈 Updates → [Follow @younghwan91](https://github.com/younghwan91)

## Related projects — open-source quant stack

Part of an open-source stack spanning Korean equities, US equities and crypto. Each repository stands on its own.

| Market | Project | What it is |
|---|---|---|
| 🇰🇷 Korean equities | **[kiwoom-rest-api](https://github.com/younghwan91/kiwoom-rest-api)** | Kiwoom Securities REST API client — full domestic-equity endpoint coverage, real-time WebSocket, sync + async (`pip install kiwoom-client`) |
| 🇰🇷 Korean equities | **[krx-fundamentals-api](https://github.com/younghwan91/krx-fundamentals-api)** | Korean corporate fundamentals REST API — financial statements, valuation, dividends, screening (DART + KRX + Naver) |
| 🇰🇷 Korean equities | **[krx-news-rest-api](https://github.com/younghwan91/krx-news-rest-api)** | Korean market news & disclosure collection API (FastAPI + Redis) |
| 🇰🇷 Korean equities | **[quant-airflow](https://github.com/younghwan91/quant-airflow)** | Airflow pipeline collecting Korean market data into TimescaleDB — delisted names included, so downstream backtests aren't survivorship-biased |
| 🇰🇷 Korean equities | **[kr-quant](https://github.com/younghwan91/kr-quant)** | KOSPI/KOSDAQ alpha research — walk-forward, random null controls, purged CV and Deflated Sharpe enforced as CI guardrails |
| 🇺🇸 US equities | **[automated-stock-trading-systems](https://github.com/younghwan91/automated-stock-trading-systems)** | Backtester for Bensdorp's seven non-correlated trading systems (educational reimplementation) |
| ₿ Crypto | **[quantbox-engine](https://github.com/younghwan91/quantbox-engine)** | Crypto futures backtest & execution engine — zero lookahead, backtest↔live parity |

## Author

**Younghwan Chae (채영환)** · [GitHub @younghwan91](https://github.com/younghwan91) · [LinkedIn](https://www.linkedin.com/in/younghwan-chae/)

The full open-source quant stack is listed on the [profile](https://github.com/younghwan91).
