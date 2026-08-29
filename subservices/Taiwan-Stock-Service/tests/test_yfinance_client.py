import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from data import yfinance_client

@patch("yfinance.Ticker")
def test_resolve_ticker_listed(mock_ticker_class):
    """Tests ticker resolution for Listed (.TW) stock."""
    # Setup mock ticker for .TW
    mock_ticker_tw = MagicMock()
    mock_ticker_tw.fast_info.last_price = 100.0
    
    mock_ticker_class.side_effect = [mock_ticker_tw]
    
    ticker, resolved = yfinance_client.resolve_ticker("2330")
    assert resolved == "2330.TW"
    assert ticker == mock_ticker_tw

@patch("yfinance.Ticker")
def test_resolve_ticker_otc(mock_ticker_class):
    """Tests fallback ticker resolution for OTC (.TWO) stock."""
    # .TW fails or is empty, .TWO succeeds
    mock_ticker_tw = MagicMock()
    # Trigger fast_info None or AttributeError to simulate invalid ticker
    type(mock_ticker_tw.fast_info).last_price = property(lambda x: exec('raise(Exception("Invalid") )'))
    
    mock_ticker_two = MagicMock()
    mock_ticker_two.fast_info.last_price = 50.0
    
    mock_ticker_class.side_effect = [mock_ticker_tw, mock_ticker_two]
    
    ticker, resolved = yfinance_client.resolve_ticker("6548")
    assert resolved == "6548.TWO"
    assert ticker == mock_ticker_two

@patch("data.yfinance_client.resolve_ticker")
def test_get_realtime_price(mock_resolve):
    """Tests formatting of realtime stock price details."""
    mock_ticker = MagicMock()
    mock_ticker.fast_info.last_price = 105.0
    mock_ticker.fast_info.previous_close = 100.0
    
    # Mock history dataframe
    hist_df = pd.DataFrame({
        "Open": [101.0],
        "High": [106.0],
        "Low": [99.0],
        "Volume": [10000]
    })
    mock_ticker.history.return_value = hist_df
    mock_ticker.info = {"longName": "台積電"}
    
    mock_resolve.return_value = (mock_ticker, "2330.TW")
    
    res = yfinance_client.get_realtime_price("2330")
    
    assert res["symbol"] == "2330"
    assert res["resolved_symbol"] == "2330.TW"
    assert res["name"] == "台積電"
    assert res["price"] == 105.0
    assert res["change"] == 5.0
    assert res["change_pct"] == 5.0
    assert res["volume"] == 10000

@patch("data.yfinance_client.resolve_ticker")
def test_get_technical_indicators(mock_resolve):
    """Tests technical indicators MA20/MA60 math based on historical close prices."""
    mock_ticker = MagicMock()
    
    # Generate 60 days of Close prices
    closes = [float(i) for i in range(1, 61)]  # 1 to 60
    hist_df = pd.DataFrame({"Close": closes})
    mock_ticker.history.return_value = hist_df
    
    mock_resolve.return_value = (mock_ticker, "2330.TW")
    
    res = yfinance_client.get_technical_indicators("2330")
    
    # Last price is 60.0
    assert res["price"] == 60.0
    # MA20: average of 41 to 60 = 50.5
    assert res["ma20"] == 50.5
    # MA60: average of 1 to 60 = 30.5
    assert res["ma60"] == 30.5
    assert res["above_ma20"] is True
    assert res["above_ma60"] is True
