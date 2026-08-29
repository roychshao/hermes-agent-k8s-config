from unittest.mock import patch, MagicMock
from data import search_client

def test_clean_html():
    """Tests HTML stripping and structural denoising (Stage 2)."""
    raw_html = """
    <html>
        <head><style>body { color: red; }</style></head>
        <body>
            <header><nav><a href="/">Home</a></nav></header>
            <main>
                <h1>奇鋐科技</h1>
                <p>奇鋐是台灣關鍵的散熱模組供應商，為輝達提供水冷技術。</p>
                <div class="ad-banner">廣告：立即點擊購買</div>
                <p>主要競爭對手包括雙鴻等散熱廠商。</p>
            </main>
            <aside>熱門文章推薦</aside>
            <footer>版權所有 © 2026</footer>
            <script>console.log('hello');</script>
        </body>
    </html>
    """
    cleaned = search_client.clean_html(raw_html.encode("utf-8"))
    
    assert "奇鋐科技" in cleaned
    assert "奇鋐是台灣關鍵的散熱模組供應商" in cleaned
    assert "主要競爭對手包括雙鴻" in cleaned
    
    # Denoised elements should be missing
    assert "Home" not in cleaned
    # Ad and boilerplate should be missing
    assert "廣告" not in cleaned
    assert "版權所有" not in cleaned
    assert "console.log" not in cleaned

def test_chunk_and_filter_text():
    """Tests keyword co-occurrence and semantic filtering (Stage 3)."""
    text = """
    奇鋐（3017）今天召開法說會，會中指出在伺服器散熱模組出貨暢旺。
    
    昨天的天氣非常好，適合出遊踏青。
    
    台積電是全球半導體代工龍頭，其製程非常先進。
    
    雙鴻（3324）也是重要的散熱模組廠，競爭力優越。
    """
    
    keywords = ["散熱", "供應鏈", "伺服器"]
    
    # Check chunks for "奇鋐"
    chunks = search_client.chunk_and_filter_text(text, "奇鋐", "3017", keywords)
    assert len(chunks) == 1
    assert "伺服器散熱模組出貨暢旺" in chunks[0]
    
    # Check chunks for a stock with no matching keywords in its paragraph
    chunks_tsmc = search_client.chunk_and_filter_text(text, "台積電", "2330", keywords)
    assert len(chunks_tsmc) == 0

@patch("requests.get")
def test_search_industry_info(mock_get):
    """
    Tests the complete search client orchestrating RSS parsing, redirect
    resolution, blacklisting, and cleaning.
    """
    # 1. Mock the RSS feed response
    mock_rss = MagicMock()
    mock_rss.status_code = 200
    mock_rss.content = """
    <rss version="2.0">
        <channel>
            <item>
                <title>奇鋐水冷散熱大爆發</title>
                <link>https://news.google.com/rss/articles/12345</link>
            </item>
            <item>
                <title>FB社交新聞</title>
                <link>https://news.google.com/rss/articles/67890</link>
            </item>
        </channel>
    </rss>
    """
    
    # 2. Mock the redirected article pages
    # Article 1 (Moneydj, whitelisted domain)
    mock_art1 = MagicMock()
    mock_art1.status_code = 200
    mock_art1.url = "https://www.moneydj.com/article/12345.html"
    mock_art1.content = "<html><body><p>奇鋐科技近期受惠於伺服器散熱與水冷模組供應鏈出貨...</p></body></html>".encode("utf-8")
    
    # Article 2 (Facebook, blacklisted domain)
    mock_art2 = MagicMock()
    mock_art2.status_code = 200
    mock_art2.url = "https://www.facebook.com/posts/67890"
    mock_art2.content = "<html><body><p>奇鋐散熱真是太厲害了，讚讚讚！</p></body></html>".encode("utf-8")
    
    # Setup mock_get side effects
    mock_get.side_effect = [mock_rss, mock_art1, mock_art2]
    
    results = search_client.search_industry_info("奇鋐", "3017", max_results=2)
    
    # Verify results
    assert len(results) == 1
    assert results[0]["title"] == "奇鋐水冷散熱大爆發"
    assert results[0]["url"] == "https://www.moneydj.com/article/12345.html"
    assert len(results[0]["chunks"]) == 1
    assert "伺服器散熱與水冷模組供應鏈出貨" in results[0]["chunks"][0]
