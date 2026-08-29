import json
import requests
import re
import urllib3
from typing import Optional, Dict, Any
from db.database import get_value_chain_cache, save_value_chain_cache

# Disable requests warnings for self-signed or missing SSL certifications on government websites
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_tpex_chain(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetches stock industry chain mapping and peers from TPEx Platform.
    Integrates a 7-day SQLite cache layer.
    """
    clean_sym = symbol.strip().split(".")[0]
    
    # 1. Try Cache First
    try:
        cached = get_value_chain_cache(clean_sym)
        if cached:
            cached["peers"] = json.loads(cached["peers_json"])
            return cached
    except Exception:
        # Gracefully fall back to live scrape if cache fails
        pass

    # 2. Live Scrape
    url = f"https://ic.tpex.org.tw/company_chain.php?stk_code={clean_sym}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        
        # Decode UTF-8 explicitly to guarantee correct traditional Chinese parsing
        html = r.content.decode("utf-8", errors="ignore")
        
        # Match main industry and subcategory
        match = re.search(r'introduce\.php\?ic=([A-Z0-9]+)[^"]*">([^<]+)</a>&nbsp;&gt;&nbsp;([^<]+)</h4>', html)
        if not match:
            match = re.search(r'introduce\.php\?ic=([A-Z0-9]+)[^"]*">([^<]+)</a>\s*&gt;\s*([^<]+)', html)
            
        if not match:
            return None
            
        ic_code = match.group(1)
        ic_name = match.group(2).strip()
        sub_name = match.group(3).strip()
        
        # Fetch industry introduce page
        intro_url = f"https://ic.tpex.org.tw/introduce.php?ic={ic_code}"
        intro_r = requests.get(intro_url, headers=headers, timeout=10)
        if intro_r.status_code != 200:
            result = {
                "industry_code": ic_code,
                "industry_name": ic_name,
                "subcategory_code": "",
                "subcategory_name": sub_name,
                "peers": []
            }
            try:
                save_value_chain_cache(clean_sym, ic_code, ic_name, "", sub_name, json.dumps([]))
            except Exception:
                pass
            return result
            
        intro_html = intro_r.content.decode("utf-8", errors="ignore")
        
        # Find the specific div for this subcategory
        pattern = rf'id="companyList_([A-Z0-9]+)" title="{re.escape(sub_name)}"'
        div_match = re.search(pattern, intro_html)
        if not div_match:
            pattern = rf'id=["\']companyList_([A-Z0-9]+)["\']\s+title=["\']{re.escape(sub_name)}["\']'
            div_match = re.search(pattern, intro_html)
            
        if not div_match:
            result = {
                "industry_code": ic_code,
                "industry_name": ic_name,
                "subcategory_code": "",
                "subcategory_name": sub_name,
                "peers": []
            }
            try:
                save_value_chain_cache(clean_sym, ic_code, ic_name, "", sub_name, json.dumps([]))
            except Exception:
                pass
            return result
            
        sub_code = div_match.group(1)
        
        # Extract the contents of that div
        start_idx = div_match.start()
        next_div = intro_html.find('id="companyList_', start_idx + 100)
        if next_div != -1:
            div_content = intro_html[start_idx:next_div]
        else:
            div_content = intro_html[start_idx:start_idx + 20000]
            
        # Parse domestic peer companies and tickers
        peers = []
        peer_matches = re.findall(r'company_basic\.php\?stk_code=(\d+)"[^>]*title="([^"]+)"', div_content)
        for ticker, name in peer_matches:
            peers.append({
                "ticker": ticker,
                "name": name,
                "type": "domestic"
            })
                
        # Parse foreign competitors
        foreign_matches = re.findall(r'href="([^"]+)"[^>]*title="([^"]+)"[^>]*target="_blank"', div_content)
        for link, name in foreign_matches:
            if "company_basic" not in link:
                peers.append({
                    "name": name,
                    "link": link,
                    "type": "foreign"
                })
                
        # Save to Cache
        try:
            save_value_chain_cache(clean_sym, ic_code, ic_name, sub_code, sub_name, json.dumps(peers, ensure_ascii=False))
        except Exception:
            pass
            
        return {
            "industry_code": ic_code,
            "industry_name": ic_name,
            "subcategory_code": sub_code,
            "subcategory_name": sub_name,
            "peers": peers
        }
    except Exception as e:
        print(f"Error scraping TPEx for {symbol}: {str(e)}")
        return None
