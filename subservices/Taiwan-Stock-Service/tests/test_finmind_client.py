import pandas as pd
from unittest.mock import patch, MagicMock
from data import finmind_client

@patch("data.finmind_client.get_data_loader")
def test_get_monthly_revenue(mock_get_dl):
    """Tests monthly revenue retrieval and YoY calculations."""
    mock_dl = MagicMock()
    
    # 2 years of revenue data for January and February
    # 2023-01-01, 2023-02-01, 2024-01-01, 2024-02-01
    df = pd.DataFrame({
        "date": ["2023-02-01", "2023-03-01", "2024-02-01", "2024-03-01"],
        "revenue_year": [2023, 2023, 2024, 2024],
        "revenue_month": [1, 2, 1, 2],
        "revenue": [100.0, 150.0, 110.0, 180.0]  # Jan YoY: 10%, Feb YoY: 20%
    })
    mock_dl.taiwan_stock_month_revenue.return_value = df
    mock_get_dl.return_value = mock_dl
    
    records = finmind_client.get_monthly_revenue("2330", months_back=2)
    
    assert len(records) == 2
    # Check latest record (Feb 2024)
    assert records[-1]["year"] == 2024
    assert records[-1]["month"] == 2
    assert records[-1]["revenue"] == 180.0
    assert records[-1]["yoy"] == 20.0  # (180 - 150) / 150 * 100
    
    # Check first record (Jan 2024)
    assert records[0]["year"] == 2024
    assert records[0]["month"] == 1
    assert records[0]["revenue"] == 110.0
    assert records[0]["yoy"] == 10.0  # (110 - 100) / 100 * 100

@patch("data.finmind_client.get_data_loader")
def test_get_quarterly_financials(mock_get_dl):
    """Tests quarterly financials statement parsing and margin/EPS calculation."""
    mock_dl = MagicMock()
    
    # Financial statements dataframe
    df = pd.DataFrame({
        "date": ["2024-03-31", "2024-03-31", "2024-03-31", "2024-03-31"],
        "type": ["Revenue", "GrossProfit", "OperatingIncome", "EPS"],
        "value": [1000.0, 500.0, 300.0, 5.0]
    })
    mock_dl.taiwan_stock_financial_statement.return_value = df
    mock_get_dl.return_value = mock_dl
    
    records = finmind_client.get_quarterly_financials("2330", quarters_back=1)
    
    assert len(records) == 1
    assert records[0]["date"] == "2024-03-31"
    assert records[0]["revenue"] == 1000.0
    assert records[0]["gross_profit_margin"] == 50.0  # 500 / 1000 * 100
    assert records[0]["operating_margin"] == 30.0  # 300 / 1000 * 100
    assert records[0]["eps"] == 5.0

@patch("data.finmind_client.get_data_loader")
def test_get_institutional_trading(mock_get_dl):
    """Tests institutional buying summation and daily grouping."""
    mock_dl = MagicMock()
    
    df = pd.DataFrame({
        "date": ["2024-08-20", "2024-08-20", "2024-08-20", "2024-08-20"],
        "name": ["Foreign_Investor", "Investment_Trust", "Dealer_self", "Dealer_Hedging"],
        "buy": [5000, 2000, 1000, 500],
        "sell": [3000, 1000, 1500, 200]
    })
    mock_dl.taiwan_stock_institutional_investors.return_value = df
    mock_get_dl.return_value = mock_dl
    
    records = finmind_client.get_institutional_trading("2330", days_back=1)
    
    assert len(records) == 1
    assert records[0]["date"] == "2024-08-20"
    assert records[0]["foreign_net_shares"] == 2000  # 5000 - 3000
    assert records[0]["trust_net_shares"] == 1000   # 2000 - 1000
    assert records[0]["dealer_net_shares"] == -200   # (1000 - 1500) + (500 - 200) = -500 + 300 = -200
    assert records[0]["total_institutional_net_shares"] == 2800  # 2000 + 1000 - 200

@patch("data.finmind_client.get_data_loader")
def test_resolve_ticker_by_name(mock_get_dl):
    """Tests resolution of ticker symbol from company name using FinMind stock info dataset."""
    mock_dl = MagicMock()
    df = pd.DataFrame({
        "stock_id": ["8111", "6488"],
        "stock_name": ["立碁", "環球晶"],
        "industry_category": ["光電業", "半導體業"]
    })
    mock_dl.taiwan_stock_info.return_value = df
    mock_get_dl.return_value = mock_dl
    
    # Test exact match
    res1 = finmind_client.resolve_ticker_by_name("立碁")
    assert res1 == "8111"
    
    # Test cleaning & fuzzy match
    res2 = finmind_client.resolve_ticker_by_name("立碁股份有限公司")
    assert res2 == "8111"
    
    # Test no match
    res3 = finmind_client.resolve_ticker_by_name("無效公司")
    assert res3 is None

@patch("data.finmind_client.get_data_loader")
def test_get_company_name_by_ticker(mock_get_dl):
    """Tests resolution of company name from ticker symbol using FinMind stock info dataset."""
    mock_dl = MagicMock()
    df = pd.DataFrame({
        "stock_id": ["8111", "6488"],
        "stock_name": ["立碁", "環球晶"]
    })
    mock_dl.taiwan_stock_info.return_value = df
    mock_get_dl.return_value = mock_dl
    
    res1 = finmind_client.get_company_name_by_ticker("8111")
    assert res1 == "立碁"
    
    res2 = finmind_client.get_company_name_by_ticker("9999")
    assert res2 is None
