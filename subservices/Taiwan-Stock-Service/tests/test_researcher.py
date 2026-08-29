import os
import pytest
from unittest.mock import patch, MagicMock
from core import researcher

@patch("core.tpex_crawler.get_tpex_chain")
@patch("data.yfinance_client.resolve_ticker")
@patch("requests.post")
@patch("db.database.add_report")
@patch("db.database.init_db")
@patch("core.screener.score_stock")
@patch("data.yfinance_client.get_realtime_price")
@patch("data.yfinance_client.get_technical_indicators")
@patch("data.finmind_client.get_monthly_revenue")
@patch("data.finmind_client.get_quarterly_financials")
@patch("data.finmind_client.get_institutional_trading")
@patch("data.finmind_client.get_stock_news")
@patch("data.search_client.search_industry_info")
@patch.dict("os.environ", {
    "LLM_API_BASE": "http://mock-gateway.internal/v1", 
    "LLM_API_KEY": "test_key",
    "LLM_MODEL": "gemini-1.5-flash"
})
def test_generate_report(mock_search, mock_news, mock_inst, mock_fin, mock_rev, 
                         mock_tech, mock_price, mock_score, mock_db_init, 
                         mock_db_report, mock_post, mock_resolve, mock_tpex):
    """
    Tests report generation using the LiteLLM API provider (HTTP requests)
    by mocking requests.post.
    """
    # 1. Setup mock data
    mock_tpex.return_value = {
        "industry_name": "半導體",
        "subcategory_name": "晶圓代工",
        "peers": [
            {"ticker": "2303", "name": "聯電", "type": "domestic"},
            {"name": "Intel", "type": "foreign"}
        ]
    }
    mock_ticker = MagicMock()
    mock_ticker.fast_info.market_cap = 500000000000
    mock_resolve.return_value = (mock_ticker, "2303.TW")

    mock_price.return_value = {
        "name": "台積電",
        "price": 600.0,
        "change": 10.0,
        "change_pct": 1.69,
        "volume": 20000000,
        "resolved_symbol": "2330.TW"
    }
    mock_score.return_value = {"total_score": 90, "tech_score": 30, "rev_score": 30, "inst_score": 30}
    mock_rev.return_value = [{"year": 2024, "month": 1, "revenue": 1000.0, "yoy": 15.0}]
    mock_fin.return_value = [{"date": "2024-03-31", "revenue": 1000.0, "gross_profit_margin": 52.0, "operating_margin": 42.0, "eps": 8.0}]
    mock_inst.return_value = [{"date": "2024-08-20", "foreign_net_shares": 1000, "trust_net_shares": 500, "total_institutional_net_shares": 1500}]
    mock_news.return_value = [{"date": "2024-08-20 10:00:00", "source": "鉅亨網", "title": "台積電水冷元件出貨大增", "link": "http://cnyes.com/123"}]
    mock_search.return_value = [{"title": "水冷散熱技術優勢", "url": "http://moneydj.com/abc", "chunks": ["台積電採用先進封裝與散熱模組"]}]

    # 2. Mock response from requests.post (OpenAI / LiteLLM JSON output)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": """---
symbol: "2330"
recommendation: "STRONG BUY"
overall_score: 90
summary: "TSMC shows robust momentum driven by AI cooling demands."
---
# TSMC Deep Dive Report
- Technicals are bullish.
- Industry position is solid.
"""
                }
            }
        ]
    }
    mock_post.return_value = mock_resp

    temp_db_path = "tests/temp_test.db"

    try:
        report_path = researcher.generate_report("2330", db_path=temp_db_path)
        
        # Verify file creation and contents
        assert os.path.exists(report_path) is True
        assert "2330" in report_path
        
        # Verify custom requests call parameters
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://mock-gateway.internal/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test_key"
        
        # Verify db interaction
        mock_db_init.assert_called_once_with(temp_db_path)
        mock_db_report.assert_called_once()
        
        # Check call args of add_report
        _, report_kwargs = mock_db_report.call_args
        assert report_kwargs["symbol"] == "2330"
        assert report_kwargs["recommendation"] == "STRONG BUY"
        assert report_kwargs["overall_score"] == 90.0
        assert report_kwargs["summary"] == "TSMC shows robust momentum driven by AI cooling demands."
        
        # Cleanup generated report file
        if os.path.exists(report_path):
            os.remove(report_path)
            
    finally:
        # Cleanup temporary database file if created
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

@patch("core.researcher.yfinance_client.get_realtime_price")
@patch("core.researcher.screener.score_stock")
@patch("core.researcher.database.init_db")
@patch("core.researcher.database.add_report")
@patch("core.researcher.finmind_client.get_monthly_revenue")
@patch("core.researcher.finmind_client.get_quarterly_financials")
@patch("core.researcher.finmind_client.get_institutional_trading")
@patch("core.researcher.finmind_client.get_stock_news")
@patch("core.researcher.search_client.search_industry_info")
@patch("core.tpex_crawler.get_tpex_chain")
@patch("data.finmind_client.resolve_ticker_by_name")
@patch("requests.post")
def test_generate_report_name_resolution(mock_post, mock_resolve_name, mock_tpex, mock_search, mock_news, mock_inst, mock_fin, mock_rev, mock_add_report, mock_db_init, mock_score, mock_price):
    mock_resolve_name.return_value = "8111"
    
    mock_price.return_value = {
        "name": "立碁",
        "price": 65.6,
        "change": 1.0,
        "change_pct": 1.5,
        "volume": 500000,
        "resolved_symbol": "8111.TWO"
    }
    mock_score.return_value = {"total_score": 15, "tech_score": 15, "rev_score": 0, "inst_score": 0}
    mock_rev.return_value = []
    mock_fin.return_value = []
    mock_inst.return_value = []
    mock_news.return_value = []
    mock_search.return_value = []
    mock_tpex.return_value = None
    mock_add_report.return_value = "reports/research/report_8111.md"
    
    # Mock LLM API post
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": """---
symbol: "8111"
recommendation: "HOLD"
overall_score: 15
summary: "立碁 1.6T 矽光子模組最快 Q4 出貨，長期看好。"
---
### Valuation Model
..."""
                }
            }
        ]
    }
    mock_post.return_value = mock_resp
    
    res_path = researcher.generate_report("立碁", db_path="tests/temp_test_res.db")
    from datetime import datetime
    expected_path = os.path.abspath(os.path.join(researcher.REPORTS_DIR, f"8111_{datetime.now().strftime('%Y%m%d')}.md"))
    assert res_path == expected_path
    mock_resolve_name.assert_called_once_with("立碁")
    
    if os.path.exists("tests/temp_test_res.db"):
        os.remove("tests/temp_test_res.db")
