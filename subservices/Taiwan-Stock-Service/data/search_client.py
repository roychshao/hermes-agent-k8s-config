import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

# Define blacklisted domains to avoid context poisoning
BLACKLISTED_DOMAINS = [
    "ptt.cc", "dcard.tw", "mobile01.com", "facebook.com", "instagram.com",
    "youtube.com", "shopee.tw", "ruten.com.tw", "momoshop.com.tw", 
    "threads.net", "x.com", "tiktok.com", "pixnet.net", "xuite.net"
]

# Define whitelisted domains to prioritize
WHITELISTED_DOMAINS = [
    "cnyes.com", "moneydj.com", "technews.tw", "udn.com", "chinatimes.com",
    "ltn.com.tw", "cw.com.tw", "wealth.com.tw", "businesstoday.com.tw",
    "commercialtimes.imarket.tw", "money.udn.com"
]

def clean_html(html_content: bytes) -> str:
    """
    Stage 2: Structural Denoising. Removes scripts, styles, navbars, footers, 
    ads, and other non-content elements from the HTML page.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Strip headers, footers, sidebars, scripts, styles, and ads
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        tag.decompose()
        
    # Remove common ad-related class or id names
    for tag in soup.find_all(class_=re.compile(r"ad-|advertisement|social-share|comment|footer|header|menu|sidebar", re.I)):
        tag.decompose()
    for tag in soup.find_all(id=re.compile(r"ad-|advertisement|social-share|comment|footer|header|menu|sidebar", re.I)):
        tag.decompose()
        
    # Extract clean text paragraphs
    paragraphs = []
    for p in soup.find_all(["p", "div", "h1", "h2", "h3", "h4"]):
        # Only extract paragraphs with actual content and skip deeply nested divs
        text = p.get_text(strip=True)
        if text:
            if p.name in ["h1", "h2", "h3", "h4"] or len(text) > 15:
                # Skip repeating text or obvious site boilerplate
                if any(boiler in text for boiler in ["著作權所有", "版權所有", "All Rights Reserved", "隱私權政策"]):
                    continue
                paragraphs.append(text)
            
    return "\n\n".join(paragraphs)

def chunk_and_filter_text(text: str, company_name: str, symbol: str, keywords: list[str]) -> list[str]:
    """
    Stage 3: Context-Aware Semantic Chunking. Splits clean text into chunks, 
    and keeps only chunks that contain the company name (or symbol) AND at least one core keyword.
    """
    # Split paragraphs using regex to robustly handle indented empty lines
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    
    # Also support splitting very long paragraphs into smaller sentences
    chunks = []
    for p in paragraphs:
        if len(p) > 600:
            # Split by common Chinese punctuation
            sentences = re.split(r"(?<=[。？！；])", p)
            current_chunk = ""
            for s in sentences:
                if len(current_chunk) + len(s) < 400:
                    current_chunk += s
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = s
            if current_chunk:
                chunks.append(current_chunk)
        else:
            chunks.append(p)
            
    filtered_chunks = []
    
    # Prepare regexes for matching
    co_regex = re.compile(rf"({re.escape(company_name)}|{re.escape(symbol)})", re.I)
    kw_patterns = [re.escape(kw) for kw in keywords]
    kw_regex = re.compile(rf"({'|'.join(kw_patterns)})", re.I) if kw_patterns else None
    
    for chunk in chunks:
        # Check company co-occurrence
        if co_regex.search(chunk):
            # Check keyword match
            if not kw_regex or kw_regex.search(chunk):
                # Clean up multiple whitespaces
                cleaned_chunk = re.sub(r"\s+", " ", chunk).strip()
                if cleaned_chunk not in filtered_chunks:
                    filtered_chunks.append(cleaned_chunk)
                    
    return filtered_chunks

def search_industry_info(company_name: str, symbol: str, keyword: str = "供應鏈 競爭優勢 散熱", 
                         max_results: int = 4) -> list[dict]:
    """
    Runs Google News RSS search for Taiwan industry context, followed by whitelisting,
    redirection resolution, BeautifulSoup HTML scraping, and semantic filtering.
    """
    query = f"{company_name} {keyword}"
    encoded_query = urllib.parse.quote_plus(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        r = requests.get(rss_url, headers=headers, timeout=10)
        r.raise_for_status()
        
        soup = BeautifulSoup(r.content, "xml")
        items = soup.find_all("item")
        
        valid_articles = []
        # Query up to double max_results to compensate for blacklisted/failed fetches
        for item in items[:max_results * 2]:
            if len(valid_articles) >= max_results:
                break
                
            title = item.title.text
            redirect_link = item.link.text
            
            try:
                # Follow the Google News redirect to fetch actual page and final URL
                art_resp = requests.get(redirect_link, headers=headers, timeout=5)
                if art_resp.status_code != 200:
                    continue
                    
                final_url = art_resp.url
                
                # Stage 1: Domain Filtering
                # Check blacklist
                if any(black in final_url.lower() for black in BLACKLISTED_DOMAINS):
                    continue
                
                # Check whitelist priority (flag it to sort later)
                is_prioritized = any(white in final_url.lower() for white in WHITELISTED_DOMAINS)
                
                # Stage 2: HTML Denoising
                clean_text = clean_html(art_resp.content)
                
                # Stage 3: Chunking & Filter
                keywords_list = ["供應鏈", "技術", "競爭", "散熱", "客戶", "份額", "優勢", "技術優勢", "合作"]
                chunks = chunk_and_filter_text(clean_text, company_name, symbol, keywords_list)
                
                if chunks:
                    valid_articles.append({
                        "title": title,
                        "url": final_url,
                        "is_prioritized": is_prioritized,
                        "chunks": chunks[:5]  # Keep top 5 relevant chunks per article
                    })
            except Exception:
                continue
                
        # Sort prioritized whitelisted domains to the top
        valid_articles.sort(key=lambda x: x["is_prioritized"], reverse=True)
        return valid_articles[:max_results]
        
    except Exception as e:
        # Return empty list if search connection fails
        return []
