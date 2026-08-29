import pytest
from unittest.mock import patch, MagicMock
import requests
from core.digitimes_crawler import (
    DigitimesCrawler,
    FreeVisitorStrategy,
    SubscriberStrategy,
    DigitimesStrategyFactory
)

def test_strategy_factory():
    # Test fallback to FreeVisitorStrategy when no credentials are in environment
    with patch.dict("os.environ", {}, clear=True):
        strat = DigitimesStrategyFactory.get_strategy()
        assert isinstance(strat, FreeVisitorStrategy)
        
    # Test SubscriberStrategy when credentials are present
    with patch.dict("os.environ", {"DIGITIMES_USERNAME": "test_user", "DIGITIMES_PASSWORD": "pwd"}):
        strat = DigitimesStrategyFactory.get_strategy()
        assert isinstance(strat, SubscriberStrategy)

@patch("requests.Session")
def test_crawler_fetch_latest_news_list(mock_session_cls):
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"""
    <html>
    <body>
    <a href="/tech/dt/n/shwnws.asp?id=0000123456_ABC">NVIDIA CoWoS demand surges</a>
    <a href="/tech/dt/n/shwnws.asp?id=0000789012_XYZ">TSMC advanced packaging shifts</a>
    </body>
    </html>
    """
    mock_session.get.return_value = mock_resp
    
    crawler = DigitimesCrawler()
    news = crawler.fetch_latest_news_list()
    
    assert len(news) == 2
    assert news[0]["id"] == "0000123456_ABC"
    assert news[0]["title"] == "NVIDIA CoWoS demand surges"
    assert "shwnws.asp" in news[0]["url"]

@patch("requests.Session")
@patch("data.search_client.search_industry_info")
def test_free_visitor_strategy(mock_search, mock_session_cls):
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"<html><body><p>TSMC has reported strong Q3 sales.</p></body></html>"
    mock_session.get.return_value = mock_resp
    
    mock_search.return_value = [
        {"title": "TSMC Q3 Report", "chunks": ["TSMC advanced packaging output increases."]}
    ]
    
    strat = FreeVisitorStrategy()
    text = strat.fetch_article_text(mock_session, "http://test.url", "TSMC Q3 Sales")
    
    assert "TSMC has reported strong" in text
    assert "TSMC advanced packaging" in text
    mock_search.assert_called_once()

@patch("requests.Session")
def test_subscriber_strategy_login_and_fetch(mock_session_cls):
    mock_session = MagicMock()
    mock_session_cls.return_value = mock_session
    
    # Mock post login response
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_session.post.return_value = mock_post_resp
    
    # Mock get article response
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.content = b"""
    <html>
    <body>
    <div id="news_txt">
    <p>TSMC premium subscriber paragraph 1.</p>
    <p>TSMC premium subscriber paragraph 2.</p>
    </div>
    </body>
    </html>
    """
    mock_session.get.return_value = mock_get_resp
    
    strat = SubscriberStrategy("user", "pass")
    text = strat.fetch_article_text(mock_session, "http://premium.url", "Premium Article")
    
    assert "TSMC premium subscriber" in text
    mock_session.post.assert_called_once()
