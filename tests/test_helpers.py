"""
Unit tests for utils.helpers — formatting and small arithmetic utilities.
"""

from __future__ import annotations

import pandas as pd
import pytest

from opt_portfolio.utils.helpers import (
    annualize_return,
    calculate_portfolio_value,
    calculate_trading_days,
    format_currency,
    format_number,
    format_percentage,
    get_color_for_value,
    validate_ticker,
)


class TestFormatters:
    def test_format_currency_default_symbol(self) -> None:
        assert format_currency(1234567.891) == "$1,234,567.89"

    def test_format_currency_custom_symbol_and_int(self) -> None:
        assert format_currency(1000, symbol="₩") == "₩1,000.00"

    def test_format_currency_negative(self) -> None:
        assert format_currency(-12.5) == "$-12.50"

    def test_format_percentage_scales_by_100(self) -> None:
        assert format_percentage(0.1234) == "12.3%"

    def test_format_percentage_decimals(self) -> None:
        assert format_percentage(0.1234, decimals=3) == "12.340%"
        assert format_percentage(-0.05, decimals=0) == "-5%"

    def test_format_number_default(self) -> None:
        assert format_number(9876543.21) == "9,876,543.21"

    def test_format_number_zero_decimals(self) -> None:
        assert format_number(2.71828, decimals=0) == "3"
        assert format_number(10, decimals=4) == "10.0000"


class TestValidateTicker:
    @pytest.mark.parametrize("ticker", ["SPY", "A", "ABCDE", "  spy ", "tlt"])
    def test_valid_tickers(self, ticker: str) -> None:
        assert validate_ticker(ticker) is True

    @pytest.mark.parametrize("ticker", ["", "   ", "ABCDEF", "BRK.B", "SPY1", "GRAF.U", "S P"])
    def test_invalid_tickers(self, ticker: str) -> None:
        assert validate_ticker(ticker) is False

    def test_non_string_rejected(self) -> None:
        assert validate_ticker(None) is False  # type: ignore[arg-type]
        assert validate_ticker(123) is False  # type: ignore[arg-type]


class TestCalculateTradingDays:
    def test_one_year_is_252(self) -> None:
        start = pd.Timestamp("2022-01-01")
        end = pd.Timestamp("2023-01-01")
        assert calculate_trading_days(start, end) == 252

    def test_same_day_is_zero(self) -> None:
        d = pd.Timestamp("2022-06-15")
        assert calculate_trading_days(d, d) == 0

    def test_reversed_dates_negative(self) -> None:
        start = pd.Timestamp("2023-01-01")
        end = pd.Timestamp("2022-01-01")
        assert calculate_trading_days(start, end) < 0

    def test_truncates_toward_zero(self) -> None:
        # 10 calendar days * 252/365 = 6.9 -> int() gives 6
        start = pd.Timestamp("2022-01-01")
        end = pd.Timestamp("2022-01-11")
        assert calculate_trading_days(start, end) == 6


class TestAnnualizeReturn:
    def test_one_year_identity(self) -> None:
        assert annualize_return(0.10, 1.0) == pytest.approx(0.10)

    def test_doubling_over_two_years(self) -> None:
        # (1 + 1.0) ** (1/2) - 1 = sqrt(2) - 1
        assert annualize_return(1.0, 2.0) == pytest.approx(2**0.5 - 1)

    def test_half_year_compounds_up(self) -> None:
        assert annualize_return(0.10, 0.5) == pytest.approx(1.1**2 - 1)

    def test_loss_stays_negative(self) -> None:
        result = annualize_return(-0.19, 2.0)
        assert result == pytest.approx(0.9 - 1)
        assert result < 0

    @pytest.mark.parametrize("years", [0.0, -1.0])
    def test_non_positive_years_returns_zero(self, years: float) -> None:
        assert annualize_return(0.5, years) == 0.0


class TestCalculatePortfolioValue:
    def test_basic_sum(self) -> None:
        holdings = {"SPY": 10, "TLT": 5}
        prices = {"SPY": 400.0, "TLT": 100.0}
        assert calculate_portfolio_value(holdings, prices) == pytest.approx(4500.0)

    def test_missing_price_is_skipped(self) -> None:
        holdings = {"SPY": 10, "GLD": 3}
        prices = {"SPY": 400.0}
        assert calculate_portfolio_value(holdings, prices) == pytest.approx(4000.0)

    def test_non_positive_shares_ignored(self) -> None:
        holdings = {"SPY": 0, "TLT": -5, "GLD": 2}
        prices = {"SPY": 400.0, "TLT": 100.0, "GLD": 180.0}
        assert calculate_portfolio_value(holdings, prices) == pytest.approx(360.0)

    def test_empty_holdings(self) -> None:
        assert calculate_portfolio_value({}, {"SPY": 400.0}) == 0.0


class TestGetColorForValue:
    def test_default_thresholds(self) -> None:
        assert get_color_for_value(1.0) == "green"
        assert get_color_for_value(-1.0) == "red"
        assert get_color_for_value(0.0) == "gray"

    def test_custom_thresholds_create_neutral_band(self) -> None:
        thresholds = (5.0, -5.0)
        assert get_color_for_value(6.0, thresholds) == "green"
        assert get_color_for_value(-6.0, thresholds) == "red"
        assert get_color_for_value(3.0, thresholds) == "gray"
        assert get_color_for_value(-3.0, thresholds) == "gray"
        # boundaries are inclusive to the neutral band
        assert get_color_for_value(5.0, thresholds) == "gray"
        assert get_color_for_value(-5.0, thresholds) == "gray"

    def test_custom_colors(self) -> None:
        colors = ("up", "flat", "down")
        assert get_color_for_value(2.0, colors=colors) == "up"
        assert get_color_for_value(0.0, colors=colors) == "flat"
        assert get_color_for_value(-2.0, colors=colors) == "down"
