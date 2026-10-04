"""
Unit tests for analysis/metrics.py — shared financial metrics functions.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from opt_portfolio.analysis.metrics import (
    calculate_cagr,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
)


class TestCalculateCagr:
    def test_known_growth(self) -> None:
        """Annual 10% CAGR over 2 years should return 0.10."""
        result = calculate_cagr(100.0, 121.0, years=2)
        assert abs(result - 0.10) < 1e-6

    def test_flat_returns_zero(self) -> None:
        result = calculate_cagr(100.0, 100.0, years=2)
        assert abs(result) < 1e-9

    def test_monotonic_growth(self) -> None:
        # 1% monthly for 60 months ≈ 12.68% CAGR
        final = 100 * (1.01**60)
        result = calculate_cagr(100.0, final, years=5)
        assert 0.12 < result < 0.14

    def test_zero_years_returns_zero(self) -> None:
        result = calculate_cagr(100.0, 120.0, years=0)
        assert result == 0.0

    def test_zero_initial_returns_zero(self) -> None:
        result = calculate_cagr(0.0, 120.0, years=1)
        assert result == 0.0

    def test_negative_years_returns_zero(self) -> None:
        result = calculate_cagr(100.0, 120.0, years=-1)
        assert result == 0.0


class TestCalculateSharpeRatio:
    def test_positive_returns_positive_sharpe(self) -> None:
        returns = pd.Series([0.02, 0.03, 0.01, 0.04, 0.02, 0.03] * 2)
        result = calculate_sharpe_ratio(returns)
        assert np.isfinite(result)
        assert result > 0

    def test_negative_returns_negative_sharpe(self) -> None:
        returns = pd.Series([-0.02, -0.03, -0.01, -0.04, -0.02, -0.03] * 2)
        result = calculate_sharpe_ratio(returns)
        assert np.isfinite(result)
        assert result < 0

    def test_zero_std_returns_zero(self) -> None:
        returns = pd.Series([0.0] * 12)
        result = calculate_sharpe_ratio(returns)
        assert result == 0.0

    @pytest.mark.parametrize("level", [0.02, -0.02, 0.005])
    def test_constant_nonzero_returns_zero_not_inf(self, level: float) -> None:
        # 상수 수익률은 변동성이 0 이라 Sharpe 가 정의되지 않는다. 예전 구현은
        # `returns.std()` 는 부동소수 오차로 0 이 아닌데 `excess.std()` 는 정확히
        # 0 이 되어 inf 를 돌려줬다 (RuntimeWarning: divide by zero).
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = calculate_sharpe_ratio(pd.Series([level] * 12))
        assert result == 0.0

    def test_single_observation_returns_zero(self) -> None:
        assert calculate_sharpe_ratio(pd.Series([0.05])) == 0.0

    def test_risk_free_subtracted(self) -> None:
        rng = np.random.default_rng(99)
        returns = pd.Series(rng.normal(0.01, 0.03, 60))
        sharpe_with_rf = calculate_sharpe_ratio(returns, risk_free_rate=0.06)
        sharpe_no_rf = calculate_sharpe_ratio(returns, risk_free_rate=0.0)
        assert sharpe_with_rf < sharpe_no_rf

    def test_empty_returns_zero(self) -> None:
        result = calculate_sharpe_ratio(pd.Series([], dtype=float))
        assert result == 0.0


class TestCalculateMaxDrawdown:
    def test_no_drawdown_flat(self) -> None:
        equity = pd.Series([100.0] * 10)
        result = calculate_max_drawdown(equity)
        assert result == 0.0

    def test_full_loss_is_near_100pct(self) -> None:
        equity = pd.Series([100.0, 50.0, 0.001])
        result = calculate_max_drawdown(equity)
        assert result > 0.99

    def test_known_drawdown(self) -> None:
        # Peak 100, trough 60 → MDD = 40%
        equity = pd.Series([100.0, 90.0, 60.0, 80.0, 110.0])
        result = calculate_max_drawdown(equity)
        assert abs(result - 0.40) < 1e-6

    def test_monotone_growth_near_zero_mdd(self) -> None:
        prices = 100 * np.cumprod(np.full(60, 1.01))
        equity = pd.Series(prices)
        result = calculate_max_drawdown(equity)
        assert result < 0.01

    def test_empty_series_returns_zero(self) -> None:
        result = calculate_max_drawdown(pd.Series([], dtype=float))
        assert result == 0.0

    def test_mdd_is_non_negative(self, sample_prices: pd.DataFrame) -> None:
        equity = sample_prices["SPY"]
        result = calculate_max_drawdown(equity)
        assert result >= 0.0
