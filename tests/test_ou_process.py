"""
Unit tests for OUForecaster — Ornstein-Uhlenbeck calibration, analytical forecast,
and Monte Carlo simulation.

All randomness is seeded. Calibration tests generate an exact discrete OU (AR(1))
series with known parameters and check the estimator recovers them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from opt_portfolio.config import MOMENTUM, OU_PROCESS
from opt_portfolio.strategies.ou_process import OUForecaster

TRUE_BETA = 0.95
TRUE_THETA = -np.log(TRUE_BETA)  # ~0.0513, inside [THETA_MIN, THETA_MAX]
TRUE_MU = 5.0
TRUE_SIGMA = 1.0


def make_ar1(
    beta: float, mu: float, sigma: float, n: int, seed: int, x0: float | None = None
) -> pd.Series:
    """Exact discrete OU: x_{t+1} = mu + beta * (x_t - mu) + sigma * eps."""
    rng = np.random.default_rng(seed)
    x = np.empty(n)
    x[0] = mu if x0 is None else x0
    eps = rng.normal(0.0, 1.0, n)
    for t in range(1, n):
        x[t] = mu + beta * (x[t - 1] - mu) + sigma * eps[t]
    index = pd.bdate_range("2015-01-01", periods=n)
    return pd.Series(x, index=index, name="X")


@pytest.fixture()
def forecaster() -> OUForecaster:
    return OUForecaster(num_simulations=1000)


@pytest.fixture()
def ou_series() -> pd.Series:
    return make_ar1(TRUE_BETA, TRUE_MU, TRUE_SIGMA, n=2000, seed=7)


class TestCalibrate:
    def test_recovers_known_parameters(
        self, forecaster: OUForecaster, ou_series: pd.Series
    ) -> None:
        params = forecaster.calibrate(ou_series)

        assert params["valid"] is True
        assert params["theta"] == pytest.approx(TRUE_THETA, abs=0.02)
        assert params["mu"] == pytest.approx(TRUE_MU, abs=1.5)
        assert params["sigma"] == pytest.approx(TRUE_SIGMA, abs=0.1)
        assert params["slope"] == pytest.approx(TRUE_BETA, abs=0.02)

    def test_theta_derived_from_slope(self, forecaster: OUForecaster, ou_series: pd.Series) -> None:
        params = forecaster.calibrate(ou_series)
        assert params["theta"] == pytest.approx(-np.log(params["slope"]))

    def test_mu_derived_from_intercept_and_slope(
        self, forecaster: OUForecaster, ou_series: pd.Series
    ) -> None:
        params = forecaster.calibrate(ou_series)
        expected_mu = params["intercept"] / (1 - params["slope"])
        assert params["mu"] == pytest.approx(expected_mu)

    def test_fast_reversion_clips_theta_to_max(self, forecaster: OUForecaster) -> None:
        # beta = 0.5 -> theta = ln 2 = 0.69, far above THETA_MAX
        fast = make_ar1(0.5, 0.0, 1.0, n=1000, seed=3)
        params = forecaster.calibrate(fast)
        assert params["slope"] == pytest.approx(0.5, abs=0.05)
        assert params["theta"] == OU_PROCESS.THETA_MAX

    def test_unit_root_clips_slope_to_max(self, forecaster: OUForecaster) -> None:
        # A pure linear trend has AR(1) slope exactly 1 -> clipped to SLOPE_MAX
        trend = pd.Series(np.arange(100, dtype=float))
        params = forecaster.calibrate(trend)
        assert params["slope"] == OU_PROCESS.SLOPE_MAX
        assert params["theta"] == pytest.approx(-np.log(OU_PROCESS.SLOPE_MAX), rel=1e-6)
        assert params["theta"] >= OU_PROCESS.THETA_MIN
        assert params["valid"] is True

    def test_short_series_returns_fallback(self, forecaster: OUForecaster) -> None:
        short = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        assert len(short) < MOMENTUM.MIN_DATA_POINTS
        params = forecaster.calibrate(short)

        assert params["valid"] is False
        assert params["theta"] == 0.01
        assert params["mu"] == pytest.approx(3.0)
        assert params["sigma"] == pytest.approx(short.std())
        assert "slope" not in params

    def test_empty_series_returns_neutral_defaults(self, forecaster: OUForecaster) -> None:
        params = forecaster.calibrate(pd.Series([], dtype=float))
        assert params == {"theta": 0.01, "mu": 0, "sigma": 1, "valid": False}

    def test_exactly_min_points_is_calibrated(self, forecaster: OUForecaster) -> None:
        series = make_ar1(TRUE_BETA, TRUE_MU, TRUE_SIGMA, n=MOMENTUM.MIN_DATA_POINTS, seed=1)
        assert forecaster.calibrate(series)["valid"] is True


class TestForecast:
    def test_above_mean_reverts_down(self, forecaster: OUForecaster, ou_series: pd.Series) -> None:
        series = ou_series.copy()
        series.iloc[-1] = TRUE_MU + 10.0
        mu_hat = forecaster.calibrate(series)["mu"]

        f1 = forecaster.forecast(series, months=1)
        assert mu_hat < f1 < series.iloc[-1]

    def test_below_mean_reverts_up(self, forecaster: OUForecaster, ou_series: pd.Series) -> None:
        series = ou_series.copy()
        series.iloc[-1] = TRUE_MU - 10.0
        mu_hat = forecaster.calibrate(series)["mu"]

        f1 = forecaster.forecast(series, months=1)
        assert series.iloc[-1] < f1 < mu_hat

    def test_longer_horizon_closer_to_mean(
        self, forecaster: OUForecaster, ou_series: pd.Series
    ) -> None:
        series = ou_series.copy()
        series.iloc[-1] = TRUE_MU + 10.0
        mu_hat = forecaster.calibrate(series)["mu"]

        gaps = [abs(forecaster.forecast(series, months=m) - mu_hat) for m in (1, 3, 6)]
        assert gaps[0] > gaps[1] > gaps[2]

    def test_matches_analytical_solution(
        self, forecaster: OUForecaster, ou_series: pd.Series
    ) -> None:
        params = forecaster.calibrate(ou_series)
        x0 = ou_series.iloc[-1]
        horizon = 3 * MOMENTUM.TRADING_DAYS_PER_MONTH
        expected = params["mu"] + (x0 - params["mu"]) * np.exp(-params["theta"] * horizon)
        assert forecaster.forecast(ou_series, months=3) == pytest.approx(expected)

    def test_short_series_returns_last_value(self, forecaster: OUForecaster) -> None:
        short = pd.Series([1.0, 2.0, 7.5])
        assert forecaster.forecast(short, months=6) == 7.5

    def test_empty_series_returns_zero(self, forecaster: OUForecaster) -> None:
        assert forecaster.forecast(pd.Series([], dtype=float)) == 0


class TestForecastDelta:
    def test_sign_follows_mean_reversion(
        self, forecaster: OUForecaster, ou_series: pd.Series
    ) -> None:
        above = ou_series.copy()
        above.iloc[-1] = TRUE_MU + 10.0
        below = ou_series.copy()
        below.iloc[-1] = TRUE_MU - 10.0

        assert forecaster.forecast_delta(above) < 0
        assert forecaster.forecast_delta(below) > 0

    def test_equals_forecast_minus_current(
        self, forecaster: OUForecaster, ou_series: pd.Series
    ) -> None:
        delta = forecaster.forecast_delta(ou_series, months=2)
        expected = forecaster.forecast(ou_series, months=2) - ou_series.iloc[-1]
        assert delta == pytest.approx(expected)

    def test_short_series_delta_is_zero(self, forecaster: OUForecaster) -> None:
        assert forecaster.forecast_delta(pd.Series([3.0, 4.0])) == 0.0
        assert forecaster.forecast_delta(pd.Series([], dtype=float)) == 0


class TestSimulate:
    def test_mean_agrees_with_analytical_forecast(
        self, forecaster: OUForecaster, ou_series: pd.Series
    ) -> None:
        np.random.seed(0)
        series = ou_series.copy()
        series.iloc[-1] = TRUE_MU + 10.0

        mean, std, paths = forecaster.simulate(series, months=1)
        analytic = forecaster.forecast(series, months=1)

        assert paths is None
        # Final-value std is ~3; 1000 paths -> standard error ~0.1
        assert mean == pytest.approx(analytic, abs=1.0)
        assert std > 0

    def test_paths_shape_and_start(self, forecaster: OUForecaster, ou_series: pd.Series) -> None:
        np.random.seed(1)
        mean, std, paths = forecaster.simulate(ou_series, months=2, return_paths=True)

        assert paths is not None
        assert paths.shape == (1000, 2 * MOMENTUM.TRADING_DAYS_PER_MONTH)
        assert np.all(paths[:, 0] == ou_series.iloc[-1])
        assert mean == pytest.approx(paths[:, -1].mean())
        assert std == pytest.approx(paths[:, -1].std())

    def test_num_simulations_respected(self, ou_series: pd.Series) -> None:
        np.random.seed(2)
        small = OUForecaster(num_simulations=50)
        _, _, paths = small.simulate(ou_series, months=1, return_paths=True)
        assert paths is not None
        assert paths.shape[0] == 50

    def test_longer_horizon_wider_spread(
        self, forecaster: OUForecaster, ou_series: pd.Series
    ) -> None:
        np.random.seed(3)
        _, std_1m, _ = forecaster.simulate(ou_series, months=1)
        np.random.seed(3)
        _, std_6m, _ = forecaster.simulate(ou_series, months=6)
        assert std_6m > std_1m

    def test_short_series_returns_current_and_zero_std(self, forecaster: OUForecaster) -> None:
        short = pd.Series([1.0, 2.0, 3.0])
        assert forecaster.simulate(short) == (3.0, 0.0, None)

    def test_empty_series(self, forecaster: OUForecaster) -> None:
        assert forecaster.simulate(pd.Series([], dtype=float)) == (0, 0.0, None)


class TestSimulateMomentumOU:
    @pytest.fixture()
    def momentum_df(self) -> pd.DataFrame:
        high = make_ar1(TRUE_BETA, 20.0, 1.0, n=200, seed=11)
        low = make_ar1(TRUE_BETA, -20.0, 1.0, n=200, seed=12)
        return pd.DataFrame({"HIGH": high.values, "LOW": low.values}, index=high.index)

    def test_higher_mean_asset_wins_most_paths(
        self, forecaster: OUForecaster, momentum_df: pd.DataFrame
    ) -> None:
        np.random.seed(4)
        probs, forecast_df = forecaster.simulate_momentum_ou(momentum_df, months=1)

        assert probs["HIGH"] > 0.9
        assert probs.sum() == pytest.approx(1.0)
        assert probs.index[0] == "HIGH"  # sorted descending
        assert list(probs.index) == ["HIGH", "LOW"]

    def test_forecast_frame_shape_and_dates(
        self, forecaster: OUForecaster, momentum_df: pd.DataFrame
    ) -> None:
        np.random.seed(5)
        months = 2
        _, forecast_df = forecaster.simulate_momentum_ou(momentum_df, months=months)

        assert forecast_df.shape == (months * MOMENTUM.TRADING_DAYS_PER_MONTH, 2)
        assert set(forecast_df.columns) == {"HIGH", "LOW"}
        assert forecast_df.index[0] > momentum_df.index[-1]
        assert forecast_df.index.freqstr == "B"
        # Mean path starts at current value and stays near each asset's mean
        assert forecast_df["HIGH"].iloc[0] == pytest.approx(momentum_df["HIGH"].iloc[-1])
        assert forecast_df["HIGH"].iloc[-1] > 10
        assert forecast_df["LOW"].iloc[-1] < -10

    def test_ticker_with_insufficient_data_is_skipped(
        self, forecaster: OUForecaster, momentum_df: pd.DataFrame
    ) -> None:
        np.random.seed(6)
        df = momentum_df.copy()
        df["SPARSE"] = np.nan
        df.iloc[-10:, df.columns.get_loc("SPARSE")] = 100.0  # only 10 valid points

        probs, forecast_df = forecaster.simulate_momentum_ou(df, months=1)

        assert probs["SPARSE"] == 0.0
        assert "SPARSE" not in forecast_df.columns
        assert probs.sum() == pytest.approx(1.0)

    def test_all_tickers_insufficient_returns_empty(self, forecaster: OUForecaster) -> None:
        df = pd.DataFrame({"A": [1.0] * 5, "B": [2.0] * 5}, index=pd.bdate_range("2020", periods=5))
        probs, forecast_df = forecaster.simulate_momentum_ou(df)
        assert probs.empty
        assert forecast_df.empty

    def test_empty_input_returns_empty(self, forecaster: OUForecaster) -> None:
        probs, forecast_df = forecaster.simulate_momentum_ou(pd.DataFrame())
        assert probs.empty
        assert forecast_df.empty


class TestGetConfidenceInterval:
    def test_bounds_bracket_mean(self, forecaster: OUForecaster, ou_series: pd.Series) -> None:
        np.random.seed(8)
        lower, mean, upper = forecaster.get_confidence_interval(ou_series, months=1)
        assert lower < mean < upper

    def test_wider_confidence_wider_interval(
        self, forecaster: OUForecaster, ou_series: pd.Series
    ) -> None:
        np.random.seed(9)
        lo95, _, hi95 = forecaster.get_confidence_interval(ou_series, confidence=0.95)
        np.random.seed(9)
        lo50, _, hi50 = forecaster.get_confidence_interval(ou_series, confidence=0.50)
        assert (hi95 - lo95) > (hi50 - lo50)

    def test_interval_roughly_matches_ou_stationary_spread(
        self, forecaster: OUForecaster, ou_series: pd.Series
    ) -> None:
        # 1-month horizon with theta ~0.05: variance ~ sigma^2 (1 - e^{-2 theta T}) / (2 theta)
        np.random.seed(10)
        params = forecaster.calibrate(ou_series)
        horizon = MOMENTUM.TRADING_DAYS_PER_MONTH
        var = (
            params["sigma"] ** 2
            * (1 - np.exp(-2 * params["theta"] * horizon))
            / (2 * params["theta"])
        )
        expected_width = 2 * 1.96 * np.sqrt(var)

        lower, _, upper = forecaster.get_confidence_interval(ou_series, months=1)
        assert (upper - lower) == pytest.approx(expected_width, rel=0.25)

    def test_short_series_collapses_to_point(self, forecaster: OUForecaster) -> None:
        short = pd.Series([1.0, 2.0, 3.0])
        assert forecaster.get_confidence_interval(short) == (3.0, 3.0, 3.0)
