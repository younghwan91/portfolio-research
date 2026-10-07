"""
Shared pytest fixtures for opt_portfolio test suite.

Provides reusable mock objects and sample DataFrames to avoid
repeated boilerplate across unit tests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture()
def sample_prices() -> pd.DataFrame:
    """Monthly price DataFrame for 4 tickers spanning 36 months."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2021-01-31", periods=36, freq="ME")
    tickers = ["SPY", "TLT", "GLD", "BIL"]

    data: dict[str, list[float]] = {}
    for ticker in tickers:
        start = {"SPY": 380.0, "TLT": 145.0, "GLD": 175.0, "BIL": 86.0}[ticker]
        drift = {"SPY": 0.007, "TLT": -0.003, "GLD": 0.002, "BIL": 0.0003}[ticker]
        vol = {"SPY": 0.04, "TLT": 0.03, "GLD": 0.025, "BIL": 0.001}[ticker]
        returns = rng.normal(drift, vol, len(dates))
        prices = start * np.cumprod(1 + returns)
        data[ticker] = prices.tolist()

    return pd.DataFrame(data, index=dates)


@pytest.fixture()
def sample_returns(sample_prices: pd.DataFrame) -> pd.DataFrame:
    """Monthly return DataFrame derived from sample_prices."""
    return sample_prices.pct_change().dropna()


@pytest.fixture()
def growing_prices() -> pd.DataFrame:
    """Monotonically growing price series — useful for deterministic metric tests."""
    dates = pd.date_range("2020-01-31", periods=60, freq="ME")
    # 1% monthly growth, no volatility
    prices = 100 * np.cumprod(np.full(60, 1.01))
    return pd.DataFrame({"ASSET": prices}, index=dates)


@pytest.fixture()
def flat_prices() -> pd.DataFrame:
    """Flat price series — should yield 0% CAGR and 0 max drawdown."""
    dates = pd.date_range("2020-01-31", periods=24, freq="ME")
    return pd.DataFrame({"ASSET": np.ones(24) * 100.0}, index=dates)


class FakeCache:
    """Stand-in for ``DataCache`` — serves a fixed daily price frame, no I/O."""

    def __init__(self, prices: pd.DataFrame) -> None:
        self.prices = prices
        self.calls: list[tuple[list[str], pd.Timestamp, pd.Timestamp]] = []

    def get_incremental_data(
        self, tickers: list[str], start: pd.Timestamp, end: pd.Timestamp
    ) -> pd.DataFrame:
        self.calls.append((list(tickers), pd.Timestamp(start), pd.Timestamp(end)))
        cols = [t for t in tickers if t in self.prices.columns]
        window = self.prices.loc[pd.Timestamp(start) : pd.Timestamp(end), cols]
        return window.copy()


def make_daily_prices(
    daily_growth: dict[str, float], end: str = "2023-12-29", periods: int = 600
) -> pd.DataFrame:
    """Deterministic constant-growth daily prices.

    ``daily_growth`` maps ticker -> per-business-day growth factor minus one
    (0.001 means +0.1 %/day, -0.001 a steady decline).  A negative growth
    rate gives negative momentum on every horizon, which is what the VAA
    defensive-switch tests need.
    """
    dates = pd.bdate_range(end=end, periods=periods)
    data = {
        ticker: 100.0 * np.cumprod(np.full(periods, 1.0 + g)) for ticker, g in daily_growth.items()
    }
    return pd.DataFrame(data, index=dates)


@pytest.fixture()
def daily_growth_prices() -> pd.DataFrame:
    """600 business days ending 2023-12-29: two risers, one faller."""
    return make_daily_prices({"SPY": 0.001, "EFA": 0.0005, "EEM": -0.001})
