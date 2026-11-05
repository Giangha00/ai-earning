"""
test_mql5_signal_crawler.py
Unit tests cho module mql5_signal_crawler.py.
Kiểm tra tính chính xác của các bộ chuyển đổi số, parsing regex,
và quy trình Feature Engineering cho AI Training Dataset.
"""

import unittest
import pandas as pd
from mql5_signal_crawler import (
    clean_number,
    parse_value_and_pct,
    parse_drawdown,
    parse_holding_time_hours,
    parse_leverage_ratio,
    MQL5SignalCrawler,
)


class TestMQL5SignalCrawlerParsers(unittest.TestCase):
    def test_clean_number(self):
        self.assertEqual(clean_number("2 343%"), 2343.0)
        self.assertEqual(clean_number("5 188.18 USD"), 5188.18)
        self.assertEqual(clean_number("-4 715.17USD"), -4715.17)
        self.assertEqual(clean_number("100.00 USD"), 100.0)
        self.assertEqual(clean_number("-"), 0.0)
        self.assertEqual(clean_number(""), 0.0)
        self.assertEqual(clean_number(None), 0.0)

    def test_parse_value_and_pct(self):
        val, pct = parse_value_and_pct("657 (71.56%)")
        self.assertEqual(val, 657.0)
        self.assertEqual(pct, 71.56)

        val, pct = parse_value_and_pct("261 (28.43%)")
        self.assertEqual(val, 261.0)
        self.assertEqual(pct, 28.43)

        val, pct = parse_value_and_pct("918")
        self.assertEqual(val, 918.0)
        self.assertEqual(pct, 0.0)

    def test_parse_drawdown(self):
        usd, pct = parse_drawdown("665.41USD (9.50%)")
        self.assertEqual(usd, 665.41)
        self.assertEqual(pct, 9.50)

        usd, pct = parse_drawdown("16.89% (319.49USD)")
        self.assertEqual(usd, 319.49)
        self.assertEqual(pct, 16.89)

    def test_parse_holding_time_hours(self):
        self.assertEqual(parse_holding_time_hours("4 hours"), 4.0)
        self.assertEqual(parse_holding_time_hours("2 days 6 hours"), 54.0)
        self.assertEqual(parse_holding_time_hours("45 mins"), 0.75)
        self.assertEqual(parse_holding_time_hours(""), 0.0)

    def test_parse_leverage_ratio(self):
        self.assertEqual(parse_leverage_ratio("1:500"), 500.0)
        self.assertEqual(parse_leverage_ratio("1:100"), 100.0)
        self.assertEqual(parse_leverage_ratio(""), 1.0)

    def test_build_ai_training_dataset(self):
        crawler = MQL5SignalCrawler(min_trades=10)
        mock_raw = pd.DataFrame([
            {
                "signal_id": "99901",
                "profit_factor": 2.2,
                "drawdown_maximal_pct": 12.0,
                "profit_trades_pct": 65.0,
                "trades_count": 250,
                "recovery_factor": 4.5,
                "average_profit_usd": 20.0,
                "average_loss_usd": -10.0,
                "profit_trades_count": 162,
                "loss_trades_count": 88,
                "annual_forecast_pct": 50.0,
                "growth_pct": 200.0,
                "profit_usd": 1500.0,
                "sharpe_ratio": 0.45,
                "weeks": 30,
            },
            {
                "signal_id": "99902",
                "profit_factor": 1.1,
                "drawdown_maximal_pct": 55.0,  # High drawdown
                "profit_trades_pct": 50.0,
                "trades_count": 120,
                "recovery_factor": 0.8,
                "average_profit_usd": 10.0,
                "average_loss_usd": -12.0,
                "profit_trades_count": 60,
                "loss_trades_count": 60,
                "annual_forecast_pct": 10.0,
                "growth_pct": 30.0,
                "profit_usd": 200.0,
                "sharpe_ratio": -0.1,
                "weeks": 10,
            }
        ])

        df_feat = crawler.build_ai_training_dataset(mock_raw)
        self.assertEqual(len(df_feat), 2)
        # Check signal 99901 (Elite/High Quality)
        row_elite = df_feat[df_feat["signal_id"] == "99901"].iloc[0]
        self.assertEqual(row_elite["is_high_quality"], 1)
        self.assertEqual(row_elite["quality_grade"], 2)
        self.assertEqual(row_elite["payoff_ratio"], 2.0)

        # Check signal 99902 (Risky / Not High Quality)
        row_risky = df_feat[df_feat["signal_id"] == "99902"].iloc[0]
        self.assertEqual(row_risky["is_high_quality"], 0)
        self.assertLess(row_risky["quality_grade"], 2)


if __name__ == "__main__":
    unittest.main()

