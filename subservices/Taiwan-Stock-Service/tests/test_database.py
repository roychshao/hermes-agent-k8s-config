import os
import tempfile
import pytest
from db import database

@pytest.fixture
def temp_db():
    """Fixture that creates a temporary database file and initializes it."""
    fd, path = tempfile.mkstemp()
    os.close(fd)
    database.init_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)

def test_is_etf():
    """Tests ETF symbol detection."""
    assert database.is_etf("0050") is True
    assert database.is_etf("0056.TW") is True
    assert database.is_etf("00878.TWO") is True
    assert database.is_etf("2330") is False
    assert database.is_etf("3017.TW") is False

def test_calculate_costs():
    """Tests brokerage fee and transaction tax calculations for Taiwan stocks."""
    # BUY 1000 shares of 2330 at 100.0, discount 0.6
    # Volume: 100,000. Fee: 100,000 * 0.001425 * 0.6 = 85.5 -> round to 86. Tax: 0
    fee, tax, total = database.calculate_costs("2330", "BUY", 1000, 100.0, 0.6)
    assert fee == 86.0
    assert tax == 0.0
    assert total == 100086.0
    
    # SELL 1000 shares of 2330 at 100.0, discount 0.6
    # Volume: 100,000. Fee: 86. Tax (Stock): 100,000 * 0.003 = 300
    fee, tax, total = database.calculate_costs("2330", "SELL", 1000, 100.0, 0.6)
    assert fee == 86.0
    assert tax == 300.0
    assert total == 100000.0 - 86.0 - 300.0 # 99614.0
    
    # SELL 1000 shares of ETF 0050 at 100.0, discount 0.6
    # Volume: 100,000. Fee: 86. Tax (ETF): 100,000 * 0.001 = 100
    fee, tax, total = database.calculate_costs("0050", "SELL", 1000, 100.0, 0.6)
    assert fee == 86.0
    assert tax == 100.0
    assert total == 100000.0 - 86.0 - 100.0 # 99814.0

def test_portfolio_accounting(temp_db):
    """
    Tests the core transaction logging and weighted-average cost PnL calculations.
    """
    # 1. First BUY: 1000 shares at 100 TWD
    # Total Cost = 100,000 + 86 (fee) = 100,086 TWD
    res1 = database.add_transaction("2330", "台積電", "BUY", 1000, 100.0, 0.6, db_path=temp_db)
    assert res1["new_quantity"] == 1000
    assert res1["new_avg_cost"] == 100.086
    assert res1["realized_pnl"] == 0.0
    
    # 2. Second BUY: 1000 shares at 120 TWD
    # Fee = 120,000 * 0.001425 * 0.6 = 102.6 -> round to 103
    # Total spent = 120,000 + 103 = 120,103 TWD
    # New avg cost = (100,086 + 120,103) / 2000 = 110.0945
    res2 = database.add_transaction("2330", "台積電", "BUY", 1000, 120.0, 0.6, db_path=temp_db)
    assert res2["new_quantity"] == 2000
    assert pytest.approx(res2["new_avg_cost"], 0.0001) == 110.0945
    assert res2["realized_pnl"] == 0.0
    
    # Check holdings in db
    holdings = database.get_portfolio(db_path=temp_db)
    assert len(holdings) == 1
    assert holdings[0]["total_quantity"] == 2000
    assert pytest.approx(holdings[0]["avg_cost"], 0.0001) == 110.0945
    
    # 3. Partial SELL: 1000 shares at 130 TWD
    # Volume: 130,000
    # Fee = 130,000 * 0.001425 * 0.6 = 111.15 -> round to 111
    # Tax = 130,000 * 0.003 = 390
    # Cash Received = 130,000 - 111 - 390 = 129,499 TWD
    # Cost Sold = 1000 * 110.0945 = 110,094.5 TWD
    # Realized PnL change = 129,499 - 110,094.5 = 19,404.5 TWD
    res3 = database.add_transaction("2330", "台積電", "SELL", 1000, 130.0, 0.6, db_path=temp_db)
    assert res3["new_quantity"] == 1000
    assert pytest.approx(res3["new_avg_cost"], 0.0001) == 110.0945
    assert pytest.approx(res3["realized_pnl"], 0.1) == 19404.5
    
    # 4. Sell out remaining position: 1000 shares at 90 TWD
    # Volume: 90,000
    # Fee = 90,000 * 0.001425 * 0.6 = 76.95 -> round to 77
    # Tax = 90,000 * 0.003 = 270
    # Cash Received = 90,000 - 77 - 270 = 89,653 TWD
    # Cost Sold = 1000 * 110.0945 = 110,094.5 TWD
    # Realized PnL change = 89,653 - 110,094.5 = -20,441.5 TWD
    # Cumulative PnL = 19,404.5 - 20,441.5 = -1,037.0 TWD
    res4 = database.add_transaction("2330", "台積電", "SELL", 1000, 90.0, 0.6, db_path=temp_db)
    assert res4["new_quantity"] == 0
    assert res4["new_avg_cost"] == 0.0
    assert pytest.approx(res4["realized_pnl"], 0.1) == -1037.0
    
    # Verify holding row persists with 0 quantity and final realized PnL
    holdings = database.get_portfolio(db_path=temp_db)
    assert len(holdings) == 1
    assert holdings[0]["total_quantity"] == 0
    assert pytest.approx(holdings[0]["realized_pnl"], 0.1) == -1037.0

def test_insufficient_position_error(temp_db):
    """Verifies database validation blocks short-selling."""
    database.add_transaction("2330", "台積電", "BUY", 100, 100.0, db_path=temp_db)
    with pytest.raises(ValueError, match="Insufficient position to sell"):
        database.add_transaction("2330", "台積電", "SELL", 101, 110.0, db_path=temp_db)

def test_report_index(temp_db):
    """Tests report indexing and retrieval."""
    database.add_report("3017", "奇鋐 report", 85.0, "BUY", "/path/to/report.md", "Very good stock", db_path=temp_db)
    reports = database.get_reports(db_path=temp_db)
    assert len(reports) == 1
    assert reports[0]["symbol"] == "3017"
    assert reports[0]["recommendation"] == "BUY"
    assert reports[0]["overall_score"] == 85.0
    assert reports[0]["file_path"] == "/path/to/report.md"
    assert reports[0]["summary"] == "Very good stock"
    
    # Filter by symbol
    reports2 = database.get_reports("2330", db_path=temp_db)
    assert len(reports2) == 0

def test_get_transactions_filtered(temp_db):
    """Tests get_transactions helper, including filtering by symbol."""
    database.add_transaction("2330", "台積電", "BUY", 100, 100.0, db_path=temp_db)
    database.add_transaction("2317", "鴻海", "BUY", 200, 100.0, db_path=temp_db)
    
    txs_all = database.get_transactions(db_path=temp_db)
    assert len(txs_all) == 2
    
    txs_2330 = database.get_transactions("2330", db_path=temp_db)
    assert len(txs_2330) == 1
    assert txs_2330[0]["symbol"] == "2330"

def test_agent_decisions(temp_db):
    """Tests saving and retrieving agent decisions."""
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    database.save_agent_decision(
        date=date_str,
        symbol="2330",
        name="台積電",
        price=100.0,
        tech_score=30,
        rev_score=35,
        inst_score=15,
        total_score=80,
        news_sentiment="BULLISH",
        news_summary="Great performance",
        selected_for_research=True,
        db_path=temp_db
    )
    
    # Retrieve within 7 days
    decisions = database.get_agent_decisions_by_days(days=7, db_path=temp_db)
    assert len(decisions) == 1
    assert decisions[0]["symbol"] == "2330"
    assert decisions[0]["news_sentiment"] == "BULLISH"
    assert decisions[0]["selected_for_research"] in (1, True)
