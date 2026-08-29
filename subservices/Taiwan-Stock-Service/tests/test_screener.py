import pytest
from unittest.mock import patch
from core import screener

@patch("data.yfinance_client.get_technical_indicators")
@patch("data.yfinance_client.get_realtime_price")
@patch("data.finmind_client.get_monthly_revenue")
@patch("data.finmind_client.get_institutional_trading")
def test_score_stock_perfect(mock_inst, mock_rev, mock_price, mock_tech):
    """
    Tests scoring a stock with perfect technical, fundamental, and institutional metrics.
    Expected: Tech (30) + Rev (35) + Inst (35) = 100 pts.
    """
    # 1. Technical momentum: price > MA20 & MA60 -> 30 pts
    mock_tech.return_value = {
        "ma20": 100.0,
        "ma60": 90.0,
        "above_ma20": True,
        "above_ma60": True
    }
    mock_price.return_value = {
        "name": "完美股",
        "price": 110.0,
        "change": 5.0,
        "change_pct": 4.76,
        "volume": 10000,
        "resolved_symbol": "9999.TW"
    }
    
    # 2. Revenue growth YoY > 20% -> 35 pts
    mock_rev.return_value = [{"yoy": 25.0}]
    
    # 3. Institutional net buying: total net > 0, and bought 5 consecutive days -> 15 + 20 = 35 pts
    mock_inst.return_value = [
        {"foreign_net_shares": 100, "trust_net_shares": 100, "total_institutional_net_shares": 200}, # Day 1
        {"foreign_net_shares": 100, "trust_net_shares": 100, "total_institutional_net_shares": 200}, # Day 2
        {"foreign_net_shares": 100, "trust_net_shares": 100, "total_institutional_net_shares": 200}, # Day 3
        {"foreign_net_shares": 100, "trust_net_shares": 100, "total_institutional_net_shares": 200}, # Day 4
        {"foreign_net_shares": 100, "trust_net_shares": 100, "total_institutional_net_shares": 200}  # Day 5
    ]
    
    res = screener.score_stock("9999")
    
    assert res["status"] == "SUCCESS"
    assert res["tech_score"] == 30
    assert res["rev_score"] == 35
    assert res["inst_score"] == 35
    assert res["total_score"] == 100

@patch("data.yfinance_client.get_technical_indicators")
@patch("data.yfinance_client.get_realtime_price")
@patch("data.finmind_client.get_monthly_revenue")
@patch("data.finmind_client.get_institutional_trading")
def test_score_stock_poor(mock_inst, mock_rev, mock_price, mock_tech):
    """
    Tests scoring a stock with poor metrics.
    Expected: Tech (0) + Rev (0) + Inst (0) = 0 pts.
    """
    mock_tech.return_value = {
        "ma20": 100.0,
        "ma60": 90.0,
        "above_ma20": False,
        "above_ma60": False
    }
    mock_price.return_value = {
        "name": "地雷股",
        "price": 80.0,
        "change": -2.0,
        "change_pct": -2.4,
        "volume": 500,
        "resolved_symbol": "0000.TW"
    }
    
    mock_rev.return_value = [{"yoy": -5.0}]
    mock_inst.return_value = [
        {"foreign_net_shares": -100, "trust_net_shares": -100, "total_institutional_net_shares": -200}
    ]
    
    res = screener.score_stock("0000")
    
    assert res["status"] == "SUCCESS"
    assert res["tech_score"] == 0
    assert res["rev_score"] == 0
    assert res["inst_score"] == 0
    assert res["total_score"] == 0

@patch("core.screener.score_stock")
def test_run_screener(mock_score):
    """Tests that screener aggregates and ranks outputs correctly."""
    mock_score.side_effect = [
        {"symbol": "AAA", "total_score": 50, "status": "SUCCESS"},
        {"symbol": "BBB", "total_score": 90, "status": "SUCCESS"},
        {"symbol": "CCC", "total_score": 10, "status": "SUCCESS"}
    ]
    
    universe = ["AAA", "BBB", "CCC"]
    results = screener.run_screener(universe)
    
    assert len(results) == 3
    # Check ranking (highest score first)
    assert results[0]["symbol"] == "BBB"
    assert results[1]["symbol"] == "AAA"
    assert results[2]["symbol"] == "CCC"

@patch("yfinance.download")
@patch("FinMind.data.DataLoader.taiwan_stock_institutional_investors")
@patch("FinMind.data.DataLoader.taiwan_stock_month_revenue")
@patch("FinMind.data.DataLoader.taiwan_stock_info")
@patch.dict("os.environ", {"FINMIND_API_TOKEN": "test_token"})
def test_run_full_market_screener_happy_path(mock_info, mock_rev, mock_inst, mock_yf):
    """
    Tests full-market batch screening with a paid/sponsor token.
    """
    import pandas as pd
    import numpy as np

    # 1. Mock active stocks info
    mock_info.return_value = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電", "industry_category": "半導體", "type": "twse", "date": "2020-06-03"},
        {"stock_id": "2317", "stock_name": "鴻海", "industry_category": "電子零組件", "type": "twse", "date": "2020-06-03"}
    ])

    # 2. Mock yfinance daily prices
    dates = pd.date_range(end="2026-08-24", periods=70)
    columns = pd.MultiIndex.from_tuples([
        ("2330.TW", "Close"),
        ("2317.TW", "Close")
    ])
    mock_yf.return_value = pd.DataFrame(
        np.random.rand(70, 2) * 100 + 500, # prices around 500-600
        index=dates,
        columns=columns
    )

    # 3. Mock FinMind monthly revenue (shows growth YoY)
    mock_rev.return_value = pd.DataFrame([
        {"stock_id": "2330", "revenue_year": 2026, "revenue_month": 7, "revenue": 1000.0, "date": "2026-08-10"},
        {"stock_id": "2330", "revenue_year": 2025, "revenue_month": 7, "revenue": 800.0, "date": "2025-08-10"},
        {"stock_id": "2317", "revenue_year": 2026, "revenue_month": 7, "revenue": 500.0, "date": "2026-08-10"},
        {"stock_id": "2317", "revenue_year": 2025, "revenue_month": 7, "revenue": 400.0, "date": "2025-08-10"}
    ])

    # 4. Mock FinMind institutional investors (positive net buy)
    mock_inst.return_value = pd.DataFrame([
        {"stock_id": "2330", "date": "2026-08-24", "name": "Foreign_Investor", "buy": 1000, "sell": 500},
        {"stock_id": "2330", "date": "2026-08-24", "name": "Investment_Trust", "buy": 500, "sell": 100},
        {"stock_id": "2317", "date": "2026-08-24", "name": "Foreign_Investor", "buy": 800, "sell": 900},
        {"stock_id": "2317", "date": "2026-08-24", "name": "Investment_Trust", "buy": 100, "sell": 50}
    ])

    results = screener.run_screener(universe=["ALL"])

    assert len(results) == 2
    assert results[0]["symbol"] in ["2330", "2317"]
    assert results[0]["status"] == "SUCCESS"
    assert results[0]["total_score"] > 0


@patch("FinMind.data.DataLoader.taiwan_stock_month_revenue")
@patch("FinMind.data.DataLoader.taiwan_stock_info")
@patch("core.screener.run_screener")
def test_run_full_market_screener_free_tier_fallback(mock_run_screener, mock_info, mock_rev):
    """
    Tests that the full-market scanner falls back to standard watchlist
    if the FinMind account is at the Free tier.
    """
    import pandas as pd

    # 1. Mock active stocks info
    mock_info.return_value = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電", "industry_category": "半導體", "type": "twse", "date": "2020-06-03"}
    ])

    # 2. Mock monthly revenue to raise the Level Free exception
    mock_rev.side_effect = Exception("FinMind API unexpected response: Your level is free. Please update your user level.")

    # 3. Setup mock fallback return
    mock_run_screener.return_value = [{"symbol": "2330", "total_score": 50, "status": "SUCCESS"}]

    results = screener.run_full_market_screener()

    # Should fall back to standard screener
    mock_run_screener.assert_called_once()
    assert results == [{"symbol": "2330", "total_score": 50, "status": "SUCCESS"}]

@patch("requests.get")
def test_fetch_top_active_tickers(mock_get):
    """
    Tests fetching the top active stock IDs from the TWSE API.
    """
    from unittest.mock import MagicMock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "stat": "OK",
        "tables": [
            {
                "title": "每日收盤行情",
                "fields": ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額"],
                "data": [
                    ["2330", "台積電", "1,000", "100", "5,000,000"],
                    ["2317", "鴻海", "2,000", "200", "8,000,000"]
                ]
            }
        ]
    }
    mock_get.return_value = mock_resp

    tickers = screener.fetch_top_active_tickers(limit=2)
    assert tickers == ["2317", "2330"]

@patch("core.screener.fetch_top_active_tickers")
@patch("core.screener.score_stock")
def test_run_screener_top_n(mock_score, mock_fetch):
    """
    Tests run_screener with a TOP10 universe keyword.
    """
    mock_fetch.return_value = ["2330", "2317"]
    mock_score.side_effect = [
        {"symbol": "2330", "total_score": 90, "status": "SUCCESS"},
        {"symbol": "2317", "total_score": 80, "status": "SUCCESS"}
    ]

    results = screener.run_screener(universe=["TOP10"])
    mock_fetch.assert_called_once_with(limit=10)
    assert len(results) == 2
    assert results[0]["symbol"] == "2330"

@patch("core.screener.score_stock")
@patch("data.finmind_client.get_stock_news")
@patch("requests.post")
@patch("db.database.init_db")
@patch("db.database.save_agent_decision")
@patch("FinMind.data.DataLoader.taiwan_stock_info")
@patch.dict("os.environ", {"LLM_API_BASE": "http://mock-api/v1", "LLM_API_KEY": "mock-key"})
def test_analyze_news_sentiment(mock_info, mock_save, mock_init, mock_post, mock_news, mock_score):
    """
    Tests analyze_news_sentiment happy path with mocked LLM and DB.
    """
    import pandas as pd
    from unittest.mock import MagicMock
    
    # Mock stock info names
    mock_info.return_value = pd.DataFrame([
        {"stock_id": "2330", "stock_name": "台積電", "industry_category": "半導體", "type": "twse", "date": "2020-06-03"}
    ])
    
    # Mock score_stock
    mock_score.return_value = {
        "status": "SUCCESS",
        "symbol": "2330",
        "name": "台積電",
        "price": 100.0,
        "tech_score": 30,
        "rev_score": 35,
        "inst_score": 15,
        "total_score": 80
    }
    
    # Mock news headlines
    mock_news.return_value = [{"title": "台積電營收亮眼"}]
    
    # Mock LLM API response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"sentiment": "BULLISH", "summary": "台積電表現優異。"}'
                }
            }
        ]
    }
    mock_post.return_value = mock_resp
    
    # Run
    results = screener.analyze_news_sentiment(["2330"])
    
    # Assert
    assert len(results) == 1
    res = results[0]
    assert res["symbol"] == "2330"
    assert res["news_sentiment"] == "BULLISH"
    assert res["news_summary"] == "台積電表現優異。"
    assert res["selected_for_research"] is True
    
    mock_save.assert_called_once()
    mock_init.assert_called_once()


