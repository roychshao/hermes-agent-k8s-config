import pytest
import json
from unittest.mock import patch, MagicMock
from core.tpex_crawler import get_tpex_chain

@patch("core.tpex_crawler.get_value_chain_cache")
def test_get_tpex_chain_cache_hit(mock_cache):
    mock_cache.return_value = {
        "symbol": "3017",
        "industry_code": "F000",
        "industry_name": "電腦及週邊設備",
        "subcategory_code": "FB00",
        "subcategory_name": "散熱片、風扇馬達、散熱模組",
        "peers_json": json.dumps([
            {"ticker": "3324", "name": "雙鴻", "type": "domestic"},
            {"name": "Intel", "link": "http://intel.com", "type": "foreign"}
        ])
    }
    
    res = get_tpex_chain("3017")
    assert res is not None
    assert res["industry_code"] == "F000"
    assert res["subcategory_name"] == "散熱片、風扇馬達、散熱模組"
    assert len(res["peers"]) == 2
    assert res["peers"][0]["ticker"] == "3324"

@patch("core.tpex_crawler.get_value_chain_cache")
@patch("requests.get")
@patch("core.tpex_crawler.save_value_chain_cache")
def test_get_tpex_chain_scrape_success(mock_save, mock_get, mock_cache):
    mock_cache.return_value = None
    
    # Mock company page response
    mock_resp1 = MagicMock()
    mock_resp1.status_code = 200
    mock_resp1.content = """
    <html>
    <body>
    <h4><a href="introduce.php?ic=F000">電腦及週邊設備</a>&nbsp;&gt;&nbsp;散熱片、風扇馬達、散熱模組</h4>
    </body>
    </html>
    """.encode("utf-8")
    
    # Mock introduce page response
    mock_resp2 = MagicMock()
    mock_resp2.status_code = 200
    mock_resp2.content = """
    <html>
    <body>
    <div id="companyList_FB00" title="散熱片、風扇馬達、散熱模組">
        <a href="company_basic.php?stk_code=3324" title="雙鴻">雙鴻</a>
        <a href="http://intel.com" title="Intel" target="_blank">Intel</a>
    </div>
    </body>
    </html>
    """.encode("utf-8")
    
    mock_get.side_effect = [mock_resp1, mock_resp2]
    
    res = get_tpex_chain("3017")
    assert res is not None
    assert res["industry_code"] == "F000"
    assert res["subcategory_code"] == "FB00"
    assert len(res["peers"]) == 2
    assert res["peers"][0]["ticker"] == "3324"
    assert res["peers"][1]["name"] == "Intel"
    mock_save.assert_called_once()

@patch("core.tpex_crawler.get_value_chain_cache")
@patch("requests.get")
def test_get_tpex_chain_failed_scrape(mock_get, mock_cache):
    mock_cache.return_value = None
    
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp
    
    res = get_tpex_chain("9999")
    assert res is None

@patch("core.tpex_crawler.get_value_chain_cache")
@patch("requests.get")
@patch("core.tpex_crawler.save_value_chain_cache")
def test_get_tpex_chain_intro_status_failed(mock_save, mock_get, mock_cache):
    mock_cache.return_value = None
    
    mock_resp1 = MagicMock()
    mock_resp1.status_code = 200
    mock_resp1.content = """
    <h4><a href="introduce.php?ic=F000">電腦及週邊設備</a>&nbsp;&gt;&nbsp;散熱片、風扇馬達、散熱模組</h4>
    """.encode("utf-8")
    
    mock_resp2 = MagicMock()
    mock_resp2.status_code = 404
    
    mock_get.side_effect = [mock_resp1, mock_resp2]
    
    res = get_tpex_chain("3017")
    assert res is not None
    assert res["subcategory_name"] == "散熱片、風扇馬達、散熱模組"
    assert len(res["peers"]) == 0
    mock_save.assert_called_once()

@patch("core.tpex_crawler.get_value_chain_cache")
@patch("requests.get")
@patch("core.tpex_crawler.save_value_chain_cache")
def test_get_tpex_chain_no_subcategory_div(mock_save, mock_get, mock_cache):
    mock_cache.return_value = None
    
    mock_resp1 = MagicMock()
    mock_resp1.status_code = 200
    mock_resp1.content = """
    <h4><a href="introduce.php?ic=F000">電腦及週邊設備</a>&nbsp;&gt;&nbsp;散熱片、風扇馬達、散熱模組</h4>
    """.encode("utf-8")
    
    mock_resp2 = MagicMock()
    mock_resp2.status_code = 200
    mock_resp2.content = """
    <html>
    <body>
    <div id="companyList_XX00" title="其他不相關分類">
        <a href="company_basic.php?stk_code=1111" title="其他公司">其他公司</a>
    </div>
    </body>
    </html>
    """.encode("utf-8")
    
    mock_get.side_effect = [mock_resp1, mock_resp2]
    
    res = get_tpex_chain("3017")
    assert res is not None
    assert len(res["peers"]) == 0
    mock_save.assert_called_once()
