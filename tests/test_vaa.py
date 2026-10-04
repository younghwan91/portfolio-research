"""
Unit tests for VAAStrategy and SelectionResult.

No network: `MomentumAnalyzer.calculate_and_rank` / `calculate_historical_momentum`
are patched on the strategy's analyzer instance, and the OU forecaster is replaced
with a mock for the ``use_forecasting=True`` tests.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from pytest_mock import MockerFixture

from opt_portfolio.config import ASSETS, AllocationMode, StrategyType
from opt_portfolio.strategies.ou_process import OUForecaster
from opt_portfolio.strategies.vaa import SelectionResult, VAAStrategy

AGG = ["SPY", "EFA", "EEM", "AGG"]
PROT = ["LQD", "IEF", "SHY"]
AS_OF = date(2023, 12, 29)


def make_ranked(scores: dict[str, float]) -> pd.DataFrame:
    """Build a ranked frame in the shape `calculate_and_rank` returns."""
    df = pd.DataFrame(
        {
            "1-Month": [s / 19 for s in scores.values()],
            "3-Month": [s / 19 for s in scores.values()],
            "6-Month": [s / 19 for s in scores.values()],
            "12-Month": [s / 19 for s in scores.values()],
            "Momentum Score": list(scores.values()),
        },
        index=list(scores.keys()),
    )
    return df.sort_values("Momentum Score", ascending=False)


def make_hist_momentum(last_row: dict[str, float], rows: int = 60) -> pd.DataFrame:
    """Flat momentum history whose final row is ``last_row``."""
    index = pd.bdate_range(end=AS_OF, periods=rows)
    return pd.DataFrame({t: [v] * rows for t, v in last_row.items()}, index=index)


@pytest.fixture()
def strategy() -> VAAStrategy:
    return VAAStrategy(
        aggressive_tickers=AGG, protective_tickers=PROT, use_cache=False, use_forecasting=False
    )


@pytest.fixture()
def growth_rankings() -> tuple[pd.DataFrame, pd.DataFrame]:
    agg = make_ranked({"SPY": 120.0, "EFA": 80.0, "EEM": 40.0, "AGG": 5.0})
    prot = make_ranked({"LQD": 30.0, "IEF": 10.0, "SHY": 2.0})
    return agg, prot


@pytest.fixture()
def defensive_rankings() -> tuple[pd.DataFrame, pd.DataFrame]:
    # SPY still has strong momentum, but EEM is negative -> VAA goes defensive
    agg = make_ranked({"SPY": 120.0, "EFA": 80.0, "EEM": -15.0, "AGG": 5.0})
    prot = make_ranked({"LQD": 30.0, "IEF": 45.0, "SHY": 2.0})
    return agg, prot


def patch_rankings(
    mocker: MockerFixture, strategy: VAAStrategy, agg: pd.DataFrame, prot: pd.DataFrame
) -> None:
    def fake_rank(tickers: list[str], end_date: date) -> tuple[pd.DataFrame, str | None]:
        if list(tickers) == strategy.aggressive_tickers:
            return agg.copy(), (agg.index[0] if not agg.empty else None)
        if list(tickers) == strategy.protective_tickers:
            return prot.copy(), (prot.index[0] if not prot.empty else None)
        raise AssertionError(f"unexpected tickers {tickers}")

    mocker.patch.object(strategy.momentum_analyzer, "calculate_and_rank", side_effect=fake_rank)


class TestSelectionResult:
    def test_defensive_flag_and_summary(self) -> None:
        result = SelectionResult("IEF", AllocationMode.DEFENSIVE, pd.DataFrame(), pd.DataFrame())
        assert result.is_defensive is True
        assert "DEFENSIVE" in result.get_summary()
        assert result.get_summary().endswith("Selected: IEF")
        assert result.strategy_recommendations is None

    def test_growth_summary(self) -> None:
        result = SelectionResult("SPY", AllocationMode.AGGRESSIVE, pd.DataFrame(), pd.DataFrame())
        assert result.is_defensive is False
        assert "GROWTH" in result.get_summary()
        assert "SPY" in result.get_summary()


class TestInit:
    def test_defaults_come_from_asset_universe(self) -> None:
        strat = VAAStrategy(use_cache=False, use_forecasting=False)
        assert strat.aggressive_tickers == list(ASSETS.AGGRESSIVE_TICKERS)
        assert strat.protective_tickers == list(ASSETS.PROTECTIVE_TICKERS)
        assert strat.forecaster is None
        assert strat.use_forecasting is False
        assert strat.momentum_analyzer.cache is None

    def test_custom_universe_copied_to_lists(self) -> None:
        strat = VAAStrategy(
            aggressive_tickers=("QQQ", "IWM"),
            protective_tickers=("BIL",),
            use_cache=False,
            use_forecasting=False,
        )
        assert strat.aggressive_tickers == ["QQQ", "IWM"]
        assert strat.protective_tickers == ["BIL"]

    def test_forecasting_enabled_builds_forecaster(self) -> None:
        strat = VAAStrategy(use_cache=False, use_forecasting=True)
        assert isinstance(strat.forecaster, OUForecaster)


class TestSelectCurrent:
    def test_growth_mode_picks_top_aggressive(
        self,
        mocker: MockerFixture,
        strategy: VAAStrategy,
        growth_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        patch_rankings(mocker, strategy, *growth_rankings)

        result = strategy.select(AS_OF)

        assert result.mode == AllocationMode.AGGRESSIVE
        assert result.is_defensive is False
        assert result.selected_etf == "SPY"
        assert list(result.aggressive_ranking.index) == ["SPY", "EFA", "EEM", "AGG"]
        assert list(result.protective_ranking.index) == ["LQD", "IEF", "SHY"]
        assert result.strategy_recommendations is None

    def test_any_negative_aggressive_switches_to_defensive(
        self,
        mocker: MockerFixture,
        strategy: VAAStrategy,
        defensive_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        patch_rankings(mocker, strategy, *defensive_rankings)

        result = strategy.select(AS_OF)

        # Core VAA rule: one negative aggressive asset -> whole portfolio to protective
        assert result.mode == AllocationMode.DEFENSIVE
        assert result.is_defensive is True
        # Top protective by momentum, not the top aggressive (SPY) despite its +120
        assert result.selected_etf == "IEF"
        assert result.selected_etf in PROT

    def test_zero_momentum_is_not_negative(
        self, mocker: MockerFixture, strategy: VAAStrategy
    ) -> None:
        agg = make_ranked({"SPY": 50.0, "EFA": 0.0, "EEM": 10.0, "AGG": 1.0})
        prot = make_ranked({"LQD": 1.0, "IEF": 2.0, "SHY": 3.0})
        patch_rankings(mocker, strategy, agg, prot)

        result = strategy.select(AS_OF)
        assert result.mode == AllocationMode.AGGRESSIVE
        assert result.selected_etf == "SPY"

    def test_empty_aggressive_ranking_raises(
        self, mocker: MockerFixture, strategy: VAAStrategy
    ) -> None:
        patch_rankings(mocker, strategy, pd.DataFrame(), make_ranked({"SHY": 1.0}))
        with pytest.raises(ValueError, match="aggressive"):
            strategy.select(AS_OF)

    def test_default_date_is_today(
        self,
        mocker: MockerFixture,
        strategy: VAAStrategy,
        growth_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        patch_rankings(mocker, strategy, *growth_rankings)
        strategy.select()

        rank_mock = strategy.momentum_analyzer.calculate_and_rank
        called_dates = {call.args[1] for call in rank_mock.call_args_list}  # type: ignore[attr-defined]
        assert called_dates == {date.today()}

    def test_both_universes_are_ranked_once(
        self,
        mocker: MockerFixture,
        strategy: VAAStrategy,
        growth_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        patch_rankings(mocker, strategy, *growth_rankings)
        strategy.select(AS_OF)

        rank_mock = strategy.momentum_analyzer.calculate_and_rank
        assert rank_mock.call_count == 2  # type: ignore[attr-defined]
        rank_mock.assert_any_call(AGG, AS_OF)  # type: ignore[attr-defined]
        rank_mock.assert_any_call(PROT, AS_OF)  # type: ignore[attr-defined]

    def test_prints_mode_and_selection(
        self,
        mocker: MockerFixture,
        strategy: VAAStrategy,
        defensive_rankings: tuple[pd.DataFrame, pd.DataFrame],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        patch_rankings(mocker, strategy, *defensive_rankings)
        strategy.select(AS_OF)

        out = capsys.readouterr().out
        assert "DEFENSIVE MODE" in out
        assert "Selected ETF: IEF" in out
        assert "Strategy Recommendations" not in out

    def test_non_current_strategy_without_forecasting_falls_back(
        self,
        mocker: MockerFixture,
        strategy: VAAStrategy,
        growth_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        patch_rankings(mocker, strategy, *growth_rankings)
        result = strategy.select(AS_OF, strategy=StrategyType.FORECAST_6M)
        assert result.selected_etf == "SPY"
        assert result.strategy_recommendations is None


class TestAnalyzeAllStrategies:
    def test_returns_one_result_per_strategy(
        self,
        mocker: MockerFixture,
        strategy: VAAStrategy,
        growth_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        patch_rankings(mocker, strategy, *growth_rankings)

        results = strategy.analyze_all_strategies(AS_OF)

        assert set(results) == set(StrategyType)
        # Without forecasting every strategy degrades to CURRENT
        assert {r.selected_etf for r in results.values()} == {"SPY"}
        assert all(r.mode == AllocationMode.AGGRESSIVE for r in results.values())


class TestSelectByStrategy:
    @pytest.fixture()
    def ranked(self) -> pd.DataFrame:
        return make_ranked({"SPY": 10.0, "EFA": 5.0})

    def test_current_ignores_recommendations(
        self, strategy: VAAStrategy, ranked: pd.DataFrame
    ) -> None:
        recs = {"Forecast_1M": {"asset": "EFA", "score": 99.0}}
        assert strategy._select_by_strategy(StrategyType.CURRENT, ranked, recs, False) == "SPY"

    def test_no_recommendations_falls_back_to_top(
        self, strategy: VAAStrategy, ranked: pd.DataFrame
    ) -> None:
        assert strategy._select_by_strategy(StrategyType.DELTA, ranked, None, False) == "SPY"
        assert strategy._select_by_strategy(StrategyType.DELTA, ranked, {}, False) == "SPY"

    @pytest.mark.parametrize(
        ("strategy_type", "key"),
        [
            (StrategyType.FORECAST_1M, "Forecast_1M"),
            (StrategyType.FORECAST_3M, "Forecast_3M"),
            (StrategyType.FORECAST_6M, "Forecast_6M"),
            (StrategyType.DELTA, "Delta"),
        ],
    )
    def test_each_strategy_reads_its_own_key(
        self,
        strategy: VAAStrategy,
        ranked: pd.DataFrame,
        strategy_type: StrategyType,
        key: str,
    ) -> None:
        recs = {key: {"asset": "EFA", "score": 1.0}, "Current": {"asset": "SPY", "score": 10.0}}
        assert strategy._select_by_strategy(strategy_type, ranked, recs, False) == "EFA"

    def test_missing_key_falls_back(self, strategy: VAAStrategy, ranked: pd.DataFrame) -> None:
        recs = {"Forecast_3M": {"asset": "EFA", "score": 1.0}}
        assert strategy._select_by_strategy(StrategyType.FORECAST_1M, ranked, recs, False) == "SPY"

    def test_key_without_asset_falls_back(
        self, strategy: VAAStrategy, ranked: pd.DataFrame
    ) -> None:
        recs = {"Forecast_1M": {"scores": {}}}
        assert strategy._select_by_strategy(StrategyType.FORECAST_1M, ranked, recs, False) == "SPY"


class TestWithForecasting:
    """`use_forecasting=True` with the OU forecaster replaced by a deterministic mock."""

    # Base scores used by the mocked forecaster, keyed by series name (= ticker)
    BASE = {"SPY": 1.0, "EFA": 9.0, "EEM": 4.0, "AGG": 2.0}

    @pytest.fixture()
    def fc_strategy(self, mocker: MockerFixture) -> VAAStrategy:
        strat = VAAStrategy(
            aggressive_tickers=AGG, protective_tickers=PROT, use_cache=False, use_forecasting=True
        )
        fake = mocker.Mock(spec=OUForecaster)
        # Forecast grows with horizon; the asset ordering is fixed by BASE
        fake.forecast.side_effect = lambda series, months=1: self.BASE[series.name] + months
        # Delta is the negative of BASE so the DELTA winner differs from the forecast winner
        fake.forecast_delta.side_effect = lambda series, months=1: -self.BASE[series.name]
        strat.forecaster = fake
        return strat

    def test_forecast_strategies_use_forecaster_ranking(
        self,
        mocker: MockerFixture,
        fc_strategy: VAAStrategy,
        growth_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        patch_rankings(mocker, fc_strategy, *growth_rankings)
        hist = make_hist_momentum({"SPY": 120.0, "EFA": 80.0, "EEM": 40.0, "AGG": 5.0}, rows=60)
        mocker.patch.object(
            fc_strategy.momentum_analyzer, "calculate_historical_momentum", return_value=hist
        )

        current = fc_strategy.select(AS_OF, StrategyType.CURRENT)
        f1 = fc_strategy.select(AS_OF, StrategyType.FORECAST_1M)
        f6 = fc_strategy.select(AS_OF, StrategyType.FORECAST_6M)
        delta = fc_strategy.select(AS_OF, StrategyType.DELTA)

        assert current.selected_etf == "SPY"  # ranked top
        assert f1.selected_etf == "EFA"  # highest mocked forecast
        assert f6.selected_etf == "EFA"
        assert delta.selected_etf == "SPY"  # least negative delta

        recs = f1.strategy_recommendations
        assert recs is not None
        assert recs["Current"] == {"asset": "SPY", "score": 120.0}
        assert recs["Forecast_1M"]["asset"] == "EFA"
        assert recs["Forecast_1M"]["score"] == pytest.approx(10.0)
        assert recs["Forecast_3M"]["score"] == pytest.approx(12.0)
        assert recs["Forecast_6M"]["score"] == pytest.approx(15.0)
        assert recs["Delta"]["asset"] == "SPY"
        assert set(recs["Forecast_1M"]["scores"]) == set(AGG)

    def test_defensive_mode_forecasts_protective_universe(
        self,
        mocker: MockerFixture,
        fc_strategy: VAAStrategy,
        defensive_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        patch_rankings(mocker, fc_strategy, *defensive_rankings)
        self.BASE.update({"LQD": 3.0, "IEF": 1.0, "SHY": 7.0})
        hist = make_hist_momentum({"LQD": 30.0, "IEF": 45.0, "SHY": 2.0}, rows=60)
        hist_mock = mocker.patch.object(
            fc_strategy.momentum_analyzer, "calculate_historical_momentum", return_value=hist
        )

        result = fc_strategy.select(AS_OF, StrategyType.FORECAST_3M)

        assert result.mode == AllocationMode.DEFENSIVE
        assert result.selected_etf == "SHY"
        tickers_arg = hist_mock.call_args.args[0]
        assert tickers_arg == PROT
        # Two-year history window ending on the calculation date
        assert hist_mock.call_args.args[2] == AS_OF
        assert (AS_OF - hist_mock.call_args.args[1]).days == 730

    def test_empty_history_yields_empty_recs_and_current_fallback(
        self,
        mocker: MockerFixture,
        fc_strategy: VAAStrategy,
        growth_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        patch_rankings(mocker, fc_strategy, *growth_rankings)
        mocker.patch.object(
            fc_strategy.momentum_analyzer,
            "calculate_historical_momentum",
            return_value=pd.DataFrame(),
        )

        result = fc_strategy.select(AS_OF, StrategyType.FORECAST_1M)
        assert result.strategy_recommendations == {}
        assert result.selected_etf == "SPY"
        fc_strategy.forecaster.forecast.assert_not_called()  # type: ignore[union-attr]

    def test_short_history_skips_forecast_keys(
        self,
        mocker: MockerFixture,
        fc_strategy: VAAStrategy,
        growth_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        patch_rankings(mocker, fc_strategy, *growth_rankings)
        hist = make_hist_momentum({"SPY": 120.0, "EFA": 80.0, "EEM": 40.0, "AGG": 5.0}, rows=20)
        mocker.patch.object(
            fc_strategy.momentum_analyzer, "calculate_historical_momentum", return_value=hist
        )

        result = fc_strategy.select(AS_OF, StrategyType.FORECAST_1M)
        recs = result.strategy_recommendations
        assert recs is not None
        assert set(recs) == {"Current"}
        assert result.selected_etf == "SPY"

    def test_recommendations_are_printed(
        self,
        mocker: MockerFixture,
        fc_strategy: VAAStrategy,
        growth_rankings: tuple[pd.DataFrame, pd.DataFrame],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        patch_rankings(mocker, fc_strategy, *growth_rankings)
        hist = make_hist_momentum({"SPY": 120.0, "EFA": 80.0, "EEM": 40.0, "AGG": 5.0}, rows=60)
        mocker.patch.object(
            fc_strategy.momentum_analyzer, "calculate_historical_momentum", return_value=hist
        )

        fc_strategy.select(AS_OF, StrategyType.FORECAST_1M)
        out = capsys.readouterr().out
        assert "Strategy Recommendations" in out
        assert "Forecast_1M: EFA" in out
        assert "Selected ETF: EFA" in out


class TestGetWinProbabilities:
    def test_disabled_forecasting_returns_empty(self, strategy: VAAStrategy) -> None:
        probs, paths = strategy.get_win_probabilities(AS_OF)
        assert probs.empty
        assert paths.empty

    def test_delegates_to_forecaster_with_active_universe(
        self,
        mocker: MockerFixture,
        defensive_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        strat = VAAStrategy(
            aggressive_tickers=AGG, protective_tickers=PROT, use_cache=False, use_forecasting=True
        )
        patch_rankings(mocker, strat, *defensive_rankings)
        hist = make_hist_momentum({"LQD": 30.0, "IEF": 45.0, "SHY": 2.0}, rows=60)
        hist_mock = mocker.patch.object(
            strat.momentum_analyzer, "calculate_historical_momentum", return_value=hist
        )
        expected_probs = pd.Series({"IEF": 0.7, "LQD": 0.3, "SHY": 0.0})
        expected_paths = pd.DataFrame({"IEF": [1.0], "LQD": [0.5], "SHY": [0.0]})
        sim_mock = mocker.patch.object(
            strat.forecaster, "simulate_momentum_ou", return_value=(expected_probs, expected_paths)
        )

        probs, paths = strat.get_win_probabilities(AS_OF, months=3)

        assert probs is expected_probs
        assert paths is expected_paths
        assert hist_mock.call_args.args[0] == PROT  # defensive -> protective universe
        sim_mock.assert_called_once_with(hist, 3)

    def test_empty_history_returns_empty(
        self,
        mocker: MockerFixture,
        growth_rankings: tuple[pd.DataFrame, pd.DataFrame],
    ) -> None:
        strat = VAAStrategy(
            aggressive_tickers=AGG, protective_tickers=PROT, use_cache=False, use_forecasting=True
        )
        patch_rankings(mocker, strat, *growth_rankings)
        hist_mock = mocker.patch.object(
            strat.momentum_analyzer, "calculate_historical_momentum", return_value=pd.DataFrame()
        )

        probs, paths = strat.get_win_probabilities()  # default date -> today

        assert probs.empty
        assert paths.empty
        assert hist_mock.call_args.args[0] == AGG
        assert hist_mock.call_args.args[2] == date.today()
