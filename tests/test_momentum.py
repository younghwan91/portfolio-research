"""
Unit tests for MomentumAnalyzer — VAA momentum calculation engine.
Tests focus on pure computation methods that don't require live data fetches.
"""

from __future__ import annotations

import logging
import sys
import types
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from dateutil.relativedelta import relativedelta

import opt_portfolio.strategies.momentum as momentum_module
from opt_portfolio.strategies.momentum import MomentumAnalyzer
from tests.conftest import FakeCache


@pytest.fixture()
def analyzer() -> MomentumAnalyzer:
    return MomentumAnalyzer(use_cache=False)


@pytest.fixture()
def daily_prices() -> pd.DataFrame:
    """Daily price data with 400 trading days for 3 tickers."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2021-01-01", periods=400)
    tickers = ["SPY", "TLT", "GLD"]
    data = {}
    for t in tickers:
        start = 100.0
        returns = rng.normal(0.0003, 0.01, len(dates))
        data[t] = start * np.cumprod(1 + returns)
    return pd.DataFrame(data, index=dates)


class TestCalculateReturns:
    def test_returns_four_periods(
        self, analyzer: MomentumAnalyzer, daily_prices: pd.DataFrame
    ) -> None:
        result = analyzer.calculate_returns(daily_prices)
        assert set(result.keys()) == {"1-Month", "3-Month", "6-Month", "12-Month"}

    def test_returns_are_percent_values(
        self, analyzer: MomentumAnalyzer, daily_prices: pd.DataFrame
    ) -> None:
        result = analyzer.calculate_returns(daily_prices)
        # Values should be percentage points (not fractions)
        vals = result["1-Month"].dropna().values.flatten()
        # Most monthly % returns should be between -50 and +50
        assert np.all(np.abs(vals[~np.isnan(vals)]) < 200)

    def test_custom_periods(self, analyzer: MomentumAnalyzer, daily_prices: pd.DataFrame) -> None:
        result = analyzer.calculate_returns(daily_prices, periods=[21, 63])
        assert len(result) == 2


class TestCalculateMomentumScore:
    def test_output_shape_matches_tickers(
        self, analyzer: MomentumAnalyzer, daily_prices: pd.DataFrame
    ) -> None:
        returns = analyzer.calculate_returns(daily_prices)
        scores = analyzer.calculate_momentum_score(returns)
        assert set(scores.columns) == {"SPY", "TLT", "GLD"}

    def test_custom_weights_applied(
        self, analyzer: MomentumAnalyzer, daily_prices: pd.DataFrame
    ) -> None:
        returns = analyzer.calculate_returns(daily_prices)
        scores_default = analyzer.calculate_momentum_score(returns)
        scores_equal = analyzer.calculate_momentum_score(returns, weights=[1, 1, 1, 1])
        # Different weights → different scores
        assert not scores_default.equals(scores_equal)

    def test_scores_finite(self, analyzer: MomentumAnalyzer, daily_prices: pd.DataFrame) -> None:
        returns = analyzer.calculate_returns(daily_prices)
        scores = analyzer.calculate_momentum_score(returns)
        assert np.all(np.isfinite(scores.values))


class TestIsNegativeMomentum:
    def test_all_positive_scores_not_defensive(self, analyzer: MomentumAnalyzer) -> None:
        ranked = pd.DataFrame(
            {
                "Ticker": ["SPY", "TLT", "GLD"],
                "Momentum Score": [10.0, 5.0, 3.0],
            }
        )
        result = analyzer.is_negative_momentum(ranked)
        assert not result

    def test_negative_scores_triggers_defensive(self, analyzer: MomentumAnalyzer) -> None:
        ranked = pd.DataFrame(
            {
                "Ticker": ["SPY", "TLT", "GLD"],
                "Momentum Score": [-10.0, -5.0, -3.0],
            }
        )
        result = analyzer.is_negative_momentum(ranked)
        assert result


class TestCalculateMomentumScoreWeighting:
    def test_default_weights_are_12_4_2_1(self, analyzer: MomentumAnalyzer) -> None:
        idx = pd.bdate_range("2022-01-03", periods=3)
        returns = {
            "1-Month": pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=idx),
            "3-Month": pd.DataFrame({"A": [2.0, 2.0, 2.0]}, index=idx),
            "6-Month": pd.DataFrame({"A": [3.0, 3.0, 3.0]}, index=idx),
            "12-Month": pd.DataFrame({"A": [4.0, 4.0, 4.0]}, index=idx),
        }
        scores = analyzer.calculate_momentum_score(returns)
        # 12*1 + 4*2 + 2*3 + 1*4 = 30
        assert np.allclose(scores["A"].values, 30.0)

    def test_rows_with_nan_are_dropped(self, analyzer: MomentumAnalyzer) -> None:
        idx = pd.bdate_range("2022-01-03", periods=3)
        base = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=idx)
        returns = {name: base.copy() for name in ["1-Month", "3-Month", "6-Month", "12-Month"]}
        returns["12-Month"].iloc[0, 0] = np.nan
        scores = analyzer.calculate_momentum_score(returns)
        assert len(scores) == 2


class TestIsNegativeMomentumEdgeCases:
    def test_missing_score_column_is_not_defensive(self, analyzer: MomentumAnalyzer) -> None:
        ranked = pd.DataFrame({"Ticker": ["SPY"], "1-Month": [-5.0]})
        assert analyzer.is_negative_momentum(ranked) is False

    def test_single_negative_among_positives(self, analyzer: MomentumAnalyzer) -> None:
        ranked = pd.DataFrame({"Momentum Score": [100.0, 50.0, -0.01]})
        assert bool(analyzer.is_negative_momentum(ranked)) is True

    def test_zero_is_not_negative(self, analyzer: MomentumAnalyzer) -> None:
        ranked = pd.DataFrame({"Momentum Score": [0.0, 10.0]})
        assert bool(analyzer.is_negative_momentum(ranked)) is False


# --- Data-fetching paths, served by the FakeCache from conftest (no DuckDB, no yfinance) ---

AS_OF = date(2023, 12, 29)


@pytest.fixture()
def cached_analyzer(
    monkeypatch: pytest.MonkeyPatch, daily_growth_prices: pd.DataFrame
) -> MomentumAnalyzer:
    fake = FakeCache(daily_growth_prices)
    monkeypatch.setattr(momentum_module, "get_cache", lambda: fake)
    analyzer = MomentumAnalyzer(use_cache=True)
    assert analyzer.cache is fake
    return analyzer


def bday_return(prices: pd.Series, months: int, end: date = AS_OF) -> float:
    """Reference return (%) the same way get_performance computes it."""
    end_ts = pd.Timestamp(end)
    start_ts = end_ts - relativedelta(months=months)
    return round((prices.loc[end_ts] / prices.asof(start_ts) - 1) * 100, 2)


class TestGetPerformance:
    def test_columns_and_index(
        self, cached_analyzer: MomentumAnalyzer, daily_growth_prices: pd.DataFrame
    ) -> None:
        perf = cached_analyzer.get_performance(["SPY", "EFA", "EEM"], AS_OF)
        assert list(perf.columns) == ["1-Month", "3-Month", "6-Month", "12-Month"]
        assert list(perf.index) == ["SPY", "EFA", "EEM"]

    def test_returns_match_reference_computation(
        self, cached_analyzer: MomentumAnalyzer, daily_growth_prices: pd.DataFrame
    ) -> None:
        perf = cached_analyzer.get_performance(["SPY"], AS_OF)
        for months in (1, 3, 6, 12):
            expected = bday_return(daily_growth_prices["SPY"], months)
            assert perf.loc["SPY", f"{months}-Month"] == pytest.approx(expected)

    def test_steady_riser_has_increasing_horizon_returns(
        self, cached_analyzer: MomentumAnalyzer
    ) -> None:
        perf = cached_analyzer.get_performance(["SPY", "EEM"], AS_OF)
        spy = perf.loc["SPY"].astype(float)
        assert spy["12-Month"] > spy["6-Month"] > spy["3-Month"] > spy["1-Month"] > 0
        eem = perf.loc["EEM"].astype(float)
        assert (eem < 0).all()

    def test_requests_thirteen_month_window(self, cached_analyzer: MomentumAnalyzer) -> None:
        cached_analyzer.get_performance(["SPY"], AS_OF)
        fake = cached_analyzer.cache
        assert isinstance(fake, FakeCache)
        tickers, start, end = fake.calls[-1]
        assert tickers == ["SPY"]
        assert end == pd.Timestamp(AS_OF)
        assert start == pd.Timestamp(AS_OF) - relativedelta(months=13)

    def test_unknown_ticker_is_skipped(self, cached_analyzer: MomentumAnalyzer) -> None:
        perf = cached_analyzer.get_performance(["SPY", "XXXX"], AS_OF)
        assert list(perf.index) == ["SPY"]

    def test_no_data_returns_empty(self, cached_analyzer: MomentumAnalyzer) -> None:
        perf = cached_analyzer.get_performance(["XXXX"], AS_OF)
        assert perf.empty

    def test_all_nan_ticker_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch, daily_growth_prices: pd.DataFrame
    ) -> None:
        prices = daily_growth_prices.copy()
        prices["DEAD"] = np.nan
        monkeypatch.setattr(momentum_module, "get_cache", lambda: FakeCache(prices))
        analyzer = MomentumAnalyzer(use_cache=True)
        perf = analyzer.get_performance(["SPY", "DEAD"], AS_OF)
        assert list(perf.index) == ["SPY"]

    def test_insufficient_history_gives_none_for_long_horizons(
        self, monkeypatch: pytest.MonkeyPatch, daily_growth_prices: pd.DataFrame
    ) -> None:
        prices = daily_growth_prices.copy()
        prices["NEW"] = np.nan
        prices.iloc[-40:, prices.columns.get_loc("NEW")] = 100.0  # ~2 months of history
        monkeypatch.setattr(momentum_module, "get_cache", lambda: FakeCache(prices))
        analyzer = MomentumAnalyzer(use_cache=True)

        perf = analyzer.get_performance(["NEW"], AS_OF)
        assert perf.loc["NEW", "1-Month"] == pytest.approx(0.0)
        # asof() before the first observation yields NaN -> stored as None -> NaN in the frame
        assert pd.isna(perf.loc["NEW", "12-Month"])
        assert pd.isna(perf.loc["NEW", "6-Month"])

    def test_no_cache_uses_yfinance_download(
        self, monkeypatch: pytest.MonkeyPatch, daily_growth_prices: pd.DataFrame
    ) -> None:
        calls: list[dict[str, object]] = []

        def fake_download(tickers: list[str], **kwargs: object) -> dict[str, pd.DataFrame]:
            calls.append({"tickers": tickers, **kwargs})
            return {"Close": daily_growth_prices}

        monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=fake_download))
        analyzer = MomentumAnalyzer(use_cache=False)
        assert analyzer.cache is None

        perf = analyzer.get_performance(["SPY", "EEM"], AS_OF)

        assert list(perf.index) == ["SPY", "EEM"]
        assert len(calls) == 1
        assert calls[0]["tickers"] == ["SPY", "EEM"]
        assert calls[0]["auto_adjust"] is True
        assert calls[0]["end"] == pd.Timestamp(AS_OF) + timedelta(days=1)


class TestCalculateAndRank:
    def test_ranks_by_weighted_score_descending(self, cached_analyzer: MomentumAnalyzer) -> None:
        ranked, top = cached_analyzer.calculate_and_rank(["EEM", "EFA", "SPY"], AS_OF)

        assert top == "SPY"
        assert list(ranked.index) == ["SPY", "EFA", "EEM"]
        assert ranked["Momentum Score"].is_monotonic_decreasing
        assert ranked.loc["EEM", "Momentum Score"] < 0 < ranked.loc["SPY", "Momentum Score"]

    def test_score_is_12_4_2_1_weighted_sum(self, cached_analyzer: MomentumAnalyzer) -> None:
        ranked, _ = cached_analyzer.calculate_and_rank(["SPY"], AS_OF)
        row = ranked.loc["SPY"]
        expected = (
            12 * row["1-Month"] + 4 * row["3-Month"] + 2 * row["6-Month"] + 1 * row["12-Month"]
        )
        assert row["Momentum Score"] == pytest.approx(expected)

    def test_score_columns_are_numeric(self, cached_analyzer: MomentumAnalyzer) -> None:
        ranked, _ = cached_analyzer.calculate_and_rank(["SPY", "EFA"], AS_OF)
        for col in ["1-Month", "3-Month", "6-Month", "12-Month", "Momentum Score"]:
            assert pd.api.types.is_numeric_dtype(ranked[col])

    def test_ticker_with_incomplete_history_is_dropped(
        self, monkeypatch: pytest.MonkeyPatch, daily_growth_prices: pd.DataFrame
    ) -> None:
        prices = daily_growth_prices.copy()
        prices["NEW"] = np.nan
        prices.iloc[-40:, prices.columns.get_loc("NEW")] = 100.0
        monkeypatch.setattr(momentum_module, "get_cache", lambda: FakeCache(prices))
        analyzer = MomentumAnalyzer(use_cache=True)

        ranked, top = analyzer.calculate_and_rank(["NEW", "SPY"], AS_OF)
        assert "NEW" not in ranked.index
        assert top == "SPY"

    def test_no_data_returns_empty_and_none(self, cached_analyzer: MomentumAnalyzer) -> None:
        ranked, top = cached_analyzer.calculate_and_rank(["XXXX"], AS_OF)
        assert ranked.empty
        assert top is None

    def test_all_rows_dropped_returns_empty_and_none(
        self, monkeypatch: pytest.MonkeyPatch, daily_growth_prices: pd.DataFrame
    ) -> None:
        prices = daily_growth_prices.copy()
        prices["NEW"] = np.nan
        prices.iloc[-40:, prices.columns.get_loc("NEW")] = 100.0
        monkeypatch.setattr(momentum_module, "get_cache", lambda: FakeCache(prices))
        analyzer = MomentumAnalyzer(use_cache=True)

        ranked, top = analyzer.calculate_and_rank(["NEW"], AS_OF)
        assert ranked.empty
        assert top is None


class TestCalculateHistoricalMomentum:
    START = date(2023, 6, 1)

    def test_output_window_and_columns(self, cached_analyzer: MomentumAnalyzer) -> None:
        hist = cached_analyzer.calculate_historical_momentum(["SPY", "EEM"], self.START, AS_OF)

        assert list(hist.columns) == ["SPY", "EEM"]
        assert hist.index.min() >= pd.Timestamp(self.START)
        assert hist.index.max() <= pd.Timestamp(AS_OF)
        assert len(hist) == len(pd.bdate_range(self.START, AS_OF))
        assert not hist.isna().any().any()

    def test_sign_follows_price_trend(self, cached_analyzer: MomentumAnalyzer) -> None:
        hist = cached_analyzer.calculate_historical_momentum(["SPY", "EEM"], self.START, AS_OF)
        assert (hist["SPY"] > 0).all()
        assert (hist["EEM"] < 0).all()

    def test_constant_growth_gives_constant_score(self, cached_analyzer: MomentumAnalyzer) -> None:
        hist = cached_analyzer.calculate_historical_momentum(["SPY"], self.START, AS_OF)
        g = 1.001
        expected = (12 * (g**21 - 1) + 4 * (g**63 - 1) + 2 * (g**126 - 1) + 1 * (g**252 - 1)) * 100
        assert np.allclose(hist["SPY"].values, expected)

    def test_fetches_400_day_buffer_before_start(self, cached_analyzer: MomentumAnalyzer) -> None:
        cached_analyzer.calculate_historical_momentum(["SPY"], self.START, AS_OF)
        fake = cached_analyzer.cache
        assert isinstance(fake, FakeCache)
        _, start, end = fake.calls[-1]
        assert start == pd.Timestamp(self.START) - timedelta(days=400)
        assert end == pd.Timestamp(AS_OF)

    def test_no_data_returns_empty(self, cached_analyzer: MomentumAnalyzer) -> None:
        hist = cached_analyzer.calculate_historical_momentum(["XXXX"], self.START, AS_OF)
        assert hist.empty

    def test_fetch_error_is_swallowed_to_empty(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        class BrokenCache:
            def get_incremental_data(self, *args: object) -> pd.DataFrame:
                raise RuntimeError("duckdb locked")

        monkeypatch.setattr(momentum_module, "get_cache", lambda: BrokenCache())
        analyzer = MomentumAnalyzer(use_cache=True)

        with caplog.at_level(logging.ERROR, logger="opt_portfolio.strategies.momentum"):
            hist = analyzer.calculate_historical_momentum(["SPY"], self.START, AS_OF)

        assert hist.empty
        assert "duckdb locked" in caplog.text

    def test_no_cache_uses_yfinance_download(
        self, monkeypatch: pytest.MonkeyPatch, daily_growth_prices: pd.DataFrame
    ) -> None:
        def fake_download(tickers: list[str], **kwargs: object) -> dict[str, pd.DataFrame]:
            return {"Close": daily_growth_prices[list(tickers)]}

        monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=fake_download))
        analyzer = MomentumAnalyzer(use_cache=False)
        hist = analyzer.calculate_historical_momentum(["SPY", "EEM"], self.START, AS_OF)
        assert list(hist.columns) == ["SPY", "EEM"]
        assert (hist["SPY"] > 0).all()


class TestCalculateMomentumSeries:
    def test_returns_lookback_rows_for_requested_tickers(
        self, analyzer: MomentumAnalyzer, daily_growth_prices: pd.DataFrame
    ) -> None:
        series = analyzer.calculate_momentum_series(daily_growth_prices, ["SPY", "EEM"], 60)
        assert series.shape == (60, 2)
        assert list(series.columns) == ["SPY", "EEM"]
        assert (series["SPY"] > 0).all()
        assert (series["EEM"] < 0).all()
        assert series.index[-1] == daily_growth_prices.index[-1]

    def test_matches_historical_momentum_formula(
        self, analyzer: MomentumAnalyzer, daily_growth_prices: pd.DataFrame
    ) -> None:
        series = analyzer.calculate_momentum_series(daily_growth_prices, ["SPY"], 10)
        g = 1.001
        expected = (12 * (g**21 - 1) + 4 * (g**63 - 1) + 2 * (g**126 - 1) + 1 * (g**252 - 1)) * 100
        assert np.allclose(series["SPY"].values, expected)

    def test_unknown_ticker_is_skipped(
        self, analyzer: MomentumAnalyzer, daily_growth_prices: pd.DataFrame
    ) -> None:
        series = analyzer.calculate_momentum_series(daily_growth_prices, ["SPY", "XXXX"], 20)
        assert list(series.columns) == ["SPY"]

    def test_too_little_history_returns_empty(
        self, analyzer: MomentumAnalyzer, daily_growth_prices: pd.DataFrame
    ) -> None:
        short = daily_growth_prices.tail(200)
        assert analyzer.calculate_momentum_series(short, ["SPY"]).empty

    def test_lookback_longer_than_available_is_truncated(
        self, analyzer: MomentumAnalyzer, daily_growth_prices: pd.DataFrame
    ) -> None:
        # 300 rows, 252 consumed by the 12-month return -> at most 48 scores
        series = analyzer.calculate_momentum_series(daily_growth_prices.tail(300), ["SPY"], 60)
        assert len(series) == 48
