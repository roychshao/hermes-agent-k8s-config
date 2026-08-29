import os
import pytest
import shutil
import tempfile
from unittest.mock import patch, MagicMock
from core.daily_digest import DailyDigestPipeline

@patch("core.screener.run_screener")
@patch("core.researcher.generate_report")
@patch("requests.post")
@patch.dict("os.environ", {
    "LLM_API_BASE": "http://mock-gateway.internal/v1", 
    "LLM_API_KEY": "test_key",
    "LLM_MODEL": "gemini-1.5-flash"
})
def test_daily_digest_pipeline(mock_post, mock_generate_report, mock_run_screener):
    # Setup mock data
    mock_run_screener.return_value = [
        {"symbol": "2330", "name": "台積電", "total_score": 90, "price": 600.0},
        {"symbol": "2317", "name": "鴻海", "total_score": 85, "price": 150.0}
    ]
    
    created_files = []
    
    def side_effect_gen(sym, db):
        fd, path = tempfile.mkstemp(suffix=f"_{sym}.md")
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(f"--- \nsymbol: \"{sym}\"\nrecommendation: \"BUY\"\n---\nReport Content for {sym}")
        created_files.append(path)
        return path
        
    mock_generate_report.side_effect = side_effect_gen
    
    # Mock LLM calls
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "# 📅 每日個股篩選與研究彙整報告\n\n## 📊 今日強勢股篩選總覽\n- 台積電\n- 鴻海"
                }
            }
        ]
    }
    mock_post.return_value = mock_resp
    
    temp_digest_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_digest_dir, "temp_digest.db")
    
    pipeline = DailyDigestPipeline(digest_dir=temp_digest_dir, db_path=temp_db_path)
    
    try:
        report_path = pipeline.run_pipeline()
        
        assert report_path is not None
        assert os.path.exists(report_path) is True
        assert "digest_" in report_path
        
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "每日個股篩選與研究彙整報告" in content
            assert "台積電" in content
            
        assert mock_generate_report.call_count == 2
        
    finally:
        # Cleanup
        for path in created_files:
            if os.path.exists(path):
                os.remove(path)
        shutil.rmtree(temp_digest_dir, ignore_errors=True)

@patch("core.screener.run_screener")
def test_daily_digest_pipeline_no_stocks(mock_run_screener):
    mock_run_screener.return_value = []
    temp_digest_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_digest_dir, "temp_digest.db")
    pipeline = DailyDigestPipeline(digest_dir=temp_digest_dir, db_path=temp_db_path)
    try:
        report_path = pipeline.run_pipeline()
        assert report_path is None
    finally:
        shutil.rmtree(temp_digest_dir, ignore_errors=True)

@patch("core.screener.run_screener")
@patch("core.researcher.generate_report")
@patch("requests.post")
def test_daily_digest_pipeline_fallback_synthesis(mock_post, mock_generate_report, mock_run_screener):
    # Setup mock data
    mock_run_screener.return_value = [
        {"symbol": "2330", "name": "台積電", "total_score": 90, "price": 600.0}
    ]
    
    created_files = []
    
    def side_effect_gen(sym, db):
        fd, path = tempfile.mkstemp(suffix=f"_{sym}.md")
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(f"--- \nsymbol: \"{sym}\"\nrecommendation: \"BUY\"\n---\nReport Content for {sym}")
        created_files.append(path)
        return path
        
    mock_generate_report.side_effect = side_effect_gen
    
    # Mock LLM API post failing (or returning empty)
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.json.side_effect = Exception("HTTP 500 Error")
    mock_post.return_value = mock_resp
    
    temp_digest_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_digest_dir, "temp_digest.db")
    
    pipeline = DailyDigestPipeline(digest_dir=temp_digest_dir, db_path=temp_db_path)
    
    try:
        report_path = pipeline.run_pipeline()
        
        assert report_path is not None
        assert os.path.exists(report_path) is True
        
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "每日個股篩選與研究彙整報告" in content
            assert "台積電" in content
            
    finally:
        for path in created_files:
            if os.path.exists(path):
                os.remove(path)
        shutil.rmtree(temp_digest_dir, ignore_errors=True)
