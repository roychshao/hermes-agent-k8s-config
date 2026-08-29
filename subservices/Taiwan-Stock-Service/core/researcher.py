import os
import re
import logging
from datetime import datetime
from dotenv import load_dotenv

from db import database
from data import yfinance_client, finmind_client, search_client
from core import screener

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DEFAULT_MODEL = os.getenv("LLM_MODEL", os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
REPORTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "reports"))

def generate_report(symbol: str, db_path: str = None) -> str:
    """
    Assembles financial data, runs web searches, invokes LiteLLM API to generate
    a professional research report, and records it in SQLite database.
    """
    api_key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("AVANTE_GEMINI_API_KEY")
    api_base = os.getenv("LLM_API_BASE")
    
    if not api_base:
        raise ValueError("LLM_API_BASE environment variable is required for LiteLLM provider.")
    if not api_key:
        raise ValueError("LLM_API_KEY (or GEMINI_API_KEY) environment variable is required.")


    # 1. Initialize SQLite Database

    if db_path is None:
        db_path = database.DEFAULT_DB_PATH
    database.init_db(db_path)
    
    clean_sym = symbol.strip().split(".")[0]
    
    # Check if the input is a Chinese company name instead of a ticker symbol
    if any(u'\u4e00' <= char <= u'\u9fff' for char in clean_sym):
        from data.finmind_client import resolve_ticker_by_name
        resolved = resolve_ticker_by_name(clean_sym)
        if resolved:
            logging.info(f"Resolved company name '{clean_sym}' to ticker symbol '{resolved}'")
            clean_sym = resolved
            
    logging.info(f"Generating research report for {clean_sym}...")
    
    # 2. Gather Data (Quantitative + Qualitative)
    # Price and Technicals
    price_info = yfinance_client.get_realtime_price(clean_sym)
    company_name = price_info["name"]
    resolved_symbol = price_info["resolved_symbol"]
    
    score_details = screener.score_stock(clean_sym)
    
    # Monthly Revenue (last 12 months)
    revenue_records = finmind_client.get_monthly_revenue(clean_sym, months_back=12)
    
    # Quarterly Financials (last 5 quarters)
    financials = finmind_client.get_quarterly_financials(clean_sym, quarters_back=5)
    
    # Institutional flows (last 5 days)
    institutions = finmind_client.get_institutional_trading(clean_sym, days_back=5)
    
    # News
    news = finmind_client.get_stock_news(clean_sym, days_back=7)
    
    # Web search for industry/supply chain advantages
    search_query = f"供應鏈 競爭力 技術優勢"
    search_articles = search_client.search_industry_info(company_name, clean_sym, search_query, max_results=4)
    
    # 2.5 Dynamic Peer Competitor Tickers Context via TPEx Value Chain Crawler
    peers_context = ""
    industry = ""
    try:
        from core.tpex_crawler import get_tpex_chain
        from data.yfinance_client import resolve_ticker
        
        tpex_data = get_tpex_chain(clean_sym)
        if tpex_data and tpex_data.get("peers"):
            ind_name = tpex_data.get("industry_name", "")
            industry = ind_name
            sub_name = tpex_data.get("subcategory_name", "")
            all_peers = tpex_data.get("peers", [])
            
            # Select top domestic peers by market cap
            domestic_peers = [p for p in all_peers if p.get("type") == "domestic"]
            foreign_peers = [p for p in all_peers if p.get("type") == "foreign"]
            
            peer_caps = []
            for p in domestic_peers:
                p_ticker = p["ticker"]
                if p_ticker == clean_sym:
                    continue
                try:
                    ticker_obj, resolved_sym = resolve_ticker(p_ticker)
                    mcap = ticker_obj.fast_info.market_cap
                    peer_caps.append((mcap if mcap else 0, p, resolved_sym))
                except Exception:
                    peer_caps.append((0, p, f"{p_ticker}.TW"))
            
            peer_caps.sort(key=lambda x: x[0], reverse=True)
            top_peers = [x[1] for x in peer_caps[:4]]
            
            def fetch_metrics(sym: str) -> dict:
                r_yoy = 0.0
                try:
                    r_records = finmind_client.get_monthly_revenue(sym, months_back=1)
                    if r_records:
                        r_yoy = r_records[-1].get("yoy", 0.0)
                except Exception:
                    pass
                
                eps_val = 0.0
                op_gr = 0.0
                marg_trend = "-"
                try:
                    q_financials = finmind_client.get_quarterly_financials(sym, quarters_back=5)
                    if q_financials:
                        eps_val = q_financials[-1].get("eps", 0.0)
                        m_list = [f"{f.get('gross_profit_margin', 0.0):.1f}%" for f in q_financials[-3:]]
                        marg_trend = " → ".join(m_list) if m_list else "-"
                        
                        if len(q_financials) >= 5:
                            latest_q = q_financials[-1]
                            prev_q = q_financials[-5]
                            latest_op = latest_q.get("revenue", 0.0) * latest_q.get("operating_margin", 0.0) / 100.0
                            prev_op = prev_q.get("revenue", 0.0) * prev_q.get("operating_margin", 0.0) / 100.0
                            
                            if prev_op > 0:
                                op_gr = ((latest_op - prev_op) / prev_op) * 100.0
                            elif latest_op > 0:
                                op_gr = 100.0
                except Exception:
                    pass
                    
                return {
                    "rev_yoy": r_yoy,
                    "eps": eps_val,
                    "op_growth": op_gr,
                    "margin_trend": marg_trend
                }
                
            target_metrics = fetch_metrics(clean_sym)
            
            peer_metrics = []
            for peer in top_peers:
                p_ticker = peer["ticker"]
                p_name = peer["name"]
                p_metrics = fetch_metrics(p_ticker)
                p_metrics["name"] = p_name
                p_metrics["ticker"] = p_ticker
                peer_metrics.append(p_metrics)
                
            avg_rev_yoy = sum(m["rev_yoy"] for m in peer_metrics) / len(peer_metrics) if peer_metrics else 0.0
            avg_eps = sum(m["eps"] for m in peer_metrics) / len(peer_metrics) if peer_metrics else 0.0
            avg_op_growth = sum(m["op_growth"] for m in peer_metrics) / len(peer_metrics) if peer_metrics else 0.0
            
            tpex_table_md = "#### 📈 核心成長與獲利指標對比 (Growth & Profitability Comparison)\n\n"
            tpex_table_md += "| 股票代號 / 名稱 | 最新月營收 YoY | 單季 EPS (元) | 營業利益成長率 | 毛利率變動趨勢 (近3季) |\n"
            tpex_table_md += "| :--- | :---: | :---: | :---: | :---: |\n"
            tpex_table_md += f"| **{clean_sym} {company_name} (本股)** | **{target_metrics['rev_yoy']:+.1f}%** | **{target_metrics['eps']:.2f}** | **{target_metrics['op_growth']:+.1f}%** | **{target_metrics['margin_trend']}** |\n"
            
            for m in peer_metrics:
                tpex_table_md += f"| {m['ticker']} {m['name']} | {m['rev_yoy']:+.1f}% | {m['eps']:.2f} | {m['op_growth']:+.1f}% | {m['margin_trend']} |\n"
                
            tpex_table_md += f"| **同業平均** | **{avg_rev_yoy:+.1f}%** | **{avg_eps:.2f}** | **{avg_op_growth:+.1f}%** | **-** |\n\n"
            
            domestic_names = [f"{p['name']} ({p['ticker']}.TW)" for p in domestic_peers if p['ticker'] != clean_sym]
            foreign_names = [f"{p['name']}" for p in foreign_peers]
            
            peers_context = f"""
=== TPEX VALUE CHAIN INFORMATION ===
Industry Category: {ind_name}
Precise Subcategory: {sub_name}
Domestic Direct Peers: {", ".join(domestic_names[:25])}
Foreign Direct Peers: {", ".join(foreign_names[:10])}

{tpex_table_md}
"""
        else:
            # Fallback to the original industry category matching
            from data.finmind_client import get_data_loader
            import pandas as pd
            dl = get_data_loader()
            df_info = dl.taiwan_stock_info()
            
            global_leaders = [
                "台積電 (TSMC, 2330.TW)", "聯電 (UMC, 2303.TW)", "聯發科 (MediaTek, 2454.TW)", 
                "鴻海 (Foxconn, 2317.TW)", "欣興 (Unimicron, 3037.TW)", "南電 (Nan Ya PCB, 8046.TW)", 
                "景碩 (Kinsus, 3189.TW)", "廣達 (Quanta Computer, 2382.TW)", "緯創 (Wistron, 3231.TW)"
            ]
            
            def extract_ticker(s: str) -> str:
                match = re.search(r"\(([^)]+)\)", s)
                if not match:
                    return ""
                content = match.group(1)
                return content.split(",")[-1].strip() if "," in content else content.strip()
                
            def get_english_names(symbols: list[str]) -> dict[str, str]:
                import concurrent.futures
                import requests
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                name_map = {}
                
                def fetch_one(sym: str) -> tuple[str, str]:
                    try:
                        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={sym}"
                        res = requests.get(url, headers=headers, timeout=5)
                        if res.status_code == 200:
                            data = res.json()
                            if "quotes" in data and len(data["quotes"]) > 0:
                                long_name = data["quotes"][0].get("longname") or data["quotes"][0].get("shortname")
                                if long_name:
                                    return sym, long_name
                    except Exception:
                        pass
                    return sym, ""
                    
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    results = executor.map(fetch_one, symbols)
                    for sym, name in results:
                        if name:
                            name_map[sym] = name
                return name_map

            target_row = df_info[df_info["stock_id"] == clean_sym]
            if not target_row.empty:
                industry = target_row["industry_category"].iloc[0]
                m_type = target_row["type"].iloc[0]
                
                df_info["stock_id_int"] = pd.to_numeric(df_info["stock_id"], errors='coerce')
                df_info = df_info.dropna(subset=["stock_id_int"]).sort_values("stock_id_int")
                
                df_peers = df_info[(df_info["industry_category"] == industry) & (df_info["type"] == m_type)]
                peer_suffix = ".TW" if m_type in ("tse", "twse") else ".TWO"
                
                df_peers_subset = df_peers[df_peers["stock_id"] != clean_sym].head(30)
                tickers_to_query = [f"{row['stock_id']}{peer_suffix}" for _, row in df_peers_subset.iterrows()]
                
                eng_names = get_english_names(tickers_to_query)
                
                peer_pairs = []
                for _, row in df_peers[df_peers["stock_id"] != clean_sym].iterrows():
                    ticker = f"{row['stock_id']}{peer_suffix}"
                    chinese_name = row['stock_name']
                    english_name = eng_names.get(ticker, "")
                    if english_name:
                        peer_pairs.append(f"{chinese_name} ({english_name}, {ticker})")
                    else:
                        peer_pairs.append(f"{chinese_name} ({ticker})")
                
                combined_peers = []
                seen = set()
                for leader in global_leaders:
                    ticker_part = extract_ticker(leader)
                    if ticker_part != f"{clean_sym}{peer_suffix}":
                        combined_peers.append(leader)
                        seen.add(ticker_part)
                        
                for peer in peer_pairs:
                    ticker_part = extract_ticker(peer)
                    if ticker_part not in seen and ticker_part != f"{clean_sym}{peer_suffix}":
                        combined_peers.append(peer)
                        seen.add(ticker_part)
                
                peers_context = f"\n=== VALID PEER COMPETITORS IN THE SAME INDUSTRY ({industry}) ===\n"
                peers_context += ", ".join(combined_peers[:50]) + "\n"
    except Exception as e:
        logging.warning(f"Failed to generate dynamic peer context: {e}")

    # 2.6 Dynamic Valuation Pre-calculation
    valuation_context = ""
    try:
        cur_price = float(price_info['price'])
        total_score = score_details['total_score']
        
        # Determine rating based on screener score
        if total_score >= 80:
            rating = "STRONG BUY"
            multiplier = 1.25  # 25% upside
        elif total_score >= 60:
            rating = "BUY"
            multiplier = 1.15  # 15% upside
        elif total_score >= 40:
            rating = "HOLD"
            multiplier = 1.0   # 0% upside
        elif total_score >= 20:
            rating = "SELL"
            multiplier = 0.85  # 15% downside
        else:
            rating = "STRONG SELL"
            multiplier = 0.70  # 30% downside
            
        target_price = cur_price * multiplier
        upside_pct = (multiplier - 1.0) * 100
        
        # Sector-specific PE multiple heuristics
        pe_multiple = 30.0
        if "半導體" in industry or "電子" in industry:
            pe_multiple = 35.0 if rating in ("STRONG BUY", "BUY") else 30.0
        else:
            pe_multiple = 20.0
            
        forward_eps = target_price / pe_multiple
        
        valuation_context = f"""
=== RECOMMENDED VALUATION MODEL DATA ===
Current Price: {cur_price:.2f} TWD
Projected Forward EPS: {forward_eps:.2f} TWD
Forward PE Multiple: {pe_multiple:.1f}x
Target Price: {target_price:.2f} TWD
Expected Upside/Downside: {upside_pct:+.2f}%
Investment Rating: {rating}
"""
    except Exception as e:
        logging.warning(f"Failed to pre-calculate valuation: {e}")

    # 3. Format Data for the LLM
    data_summary = f"""
=== STOCK OVERVIEW ===
Symbol: {resolved_symbol} (Original query: {symbol})
Name: {company_name}
Current Price: {price_info['price']} TWD
Change: {price_info['change']} TWD ({price_info['change_pct']:.2f}%)
Daily Volume: {price_info['volume']} shares
Shares Outstanding: {price_info.get('shares', 0):,} shares
Market Capitalization: {price_info.get('market_cap', 0):,} TWD

=== QUANTITATIVE SCORES ===
Overall Screener Score: {score_details['total_score']} / 100
- Technical Score (MA20/MA60): {score_details['tech_score']} / 30
- Monthly Revenue Score: {score_details['rev_score']} / 35
- Institutional Buying Score: {score_details['inst_score']} / 35

=== REVENUE TREND (LATEST MONTHS) ===
"""
    for r in revenue_records[-6:]:
        data_summary += f"- {r['year']}-{r['month']:02d}: Revenue {r['revenue']:,} TWD, YoY Growth: {r['yoy']:.2f}%\n"
        
    data_summary += "\n=== QUARTERLY FINANCIALS ===\n"
    for f in financials:
        data_summary += f"- Date {f['date']}: Gross Margin: {f['gross_profit_margin']:.2f}%, Operating Margin: {f['operating_margin']:.2f}%, EPS: {f['eps']} TWD\n"
        
    data_summary += "\n=== INSTITUTIONAL TRADING (LAST 5 DAYS) ===\n"
    for inst in institutions:
        data_summary += f"- Date {inst['date']}: Foreign Net: {inst['foreign_net_shares']:,} shares, Trust Net: {inst['trust_net_shares']:,} shares, Total Net: {inst['total_institutional_net_shares']:,} shares\n"
        
    data_summary += "\n=== RECENT NEWS HEADLINES ===\n"
    if news:
        for idx, item in enumerate(news[:6]):
            data_summary += f"{idx+1}. [{item['date']}] {item['title']} (Source: {item['source']})\n"
    else:
        data_summary += "No recent news found.\n"
        
    data_summary += "\n=== INDUSTRY SUPPLY CHAIN WEB SEARCH CONTEXT ===\n"
    if search_articles:
        for art in search_articles:
            data_summary += f"Source URL: {art['url']}\n"
            data_summary += f"Title: {art['title']}\n"
            data_summary += "Relevant Facts extracted:\n"
            for chunk in art["chunks"]:
                data_summary += f"- {chunk}\n"
            data_summary += "\n"
    else:
        data_summary += "No additional qualitative supply chain search data found.\n"
        
    data_summary += peers_context
    data_summary += valuation_context
        
    now = datetime.now()
    current_date_str = now.strftime("%Y年%m月%d日")
    current_year = now.year
    
    # 4. Prompt Engineering
    system_prompt = f"""You are a Senior Buy-side Equity Research Analyst specializing in the Taiwan stock market (台股). Your goal is to analyze the provided stock data and write a highly objective, data-driven, and insightful investment report.
The current date of report generation is {current_date_str}. The current year is {current_year}.
Any timeline analyses or projections must be relative to {current_year} (e.g. Q4 {current_year} is immediate, {current_year + 1} is mid-term).

You must follow this Chain-of-Thought reasoning process before writing the report:
1. Data Fact-Check: Review all quantitative data (revenue, margins, institutional flows, moving averages).
2. Industry & Supply Chain Analysis: Define the company's position in the industry supply chain, its technical advantages, and key competitors based on the provided search results.
3. Sentiment & Catalysts: Analyze recent news headlines and sentiment. What are the growth drivers or red flags?
4. Reconcile Contradictions: If the company has strong revenue but heavy institutional selling (or vice versa), explain the likely causes.
5. Rating Decision: Assign a rating (Strong Buy, Buy, Hold, Sell, Strong Sell) based on both quantitative metrics and qualitative supply chain advantages.

Tone: Professional, objective, analytical. Avoid emotional exaggerations. Cite specific numbers and percentages.

You MUST write the report in Markdown.
At the very beginning of the report, you MUST output a YAML frontmatter block containing exactly the following keys:
---
symbol: "[symbol]"
recommendation: "[STRONG BUY / BUY / HOLD / SELL / STRONG SELL]"
overall_score: [screener score from data]
summary: "[A single sentence summarizing the investment thesis]"
---
Do not include any text before this frontmatter.

Strict Guidelines to avoid common errors:
1. Cleanliness of Output (No Internal Dialogue):
   Do NOT output your Chain-of-Thought reasoning, internal dialogues, draft notes, self-questioning, or logical struggles in the final Markdown report. The output report must be a polished, cohesive, and consistent professional document. Resolve all your calculations internally before writing the output.
   - Do NOT quote these prompt instructions, guidelines, or meta-rules anywhere in the output report.
   - Your 'Valuation & Target Price' section MUST follow a strict structure and contain ONLY the following subheaders and content, with no conversational filler, meta-reasoning, or draft notes:
   ### Valuation Model
   [Describe the Forward PE model and Forward EPS estimation (e.g., Forward EPS of X TWD based on Y growth)]
   ### Forward PE Multiple
   [State the chosen multiplier, e.g., Zx, and the reason]
   ### Target Price & Upside
   - Current Price: [Price] TWD
   - Projected Forward EPS: [EPS] TWD
   - Forward PE Multiple: [Multiple]x
   - Target Price: [Target Price] TWD
   - Expected Upside/Downside: [Upside]%
   - Investment Rating: [Rating]
   Do NOT write any conversational text under these sections. Ensure all calculations are completed internally before outputting the final numbers.

2. Peer Stock Codes and Names Verification:
   Do NOT guess or hallucinate Taiwan stock ticker codes. If you mention peer competitors, verify and use ONLY correct ones listed in the 'VALID PEER COMPETITORS IN THE SAME INDUSTRY' section provided in the stock data context. 
   - Always write a company's Chinese name and English name together, followed by the correct ticker code from the context (e.g. 欣興 (Unimicron, 3037.TW), 景碩 (Kinsus, 3189.TW)).
   - Do NOT translate or invent new English names.
   - Do NOT mix up tickers: 3711.TW is ASE Technology Holding (日月光投控), NOT Unimicron.
   - If a company is not listed in the context, state the company name only and DO NOT append '.TW' or '.TWO' with a guessed number.

3. Valuation & Target Price (Forward PE Model):
   You MUST include a dedicated 'Valuation & Target Price' section in the report following the structure in Guideline 1.
   - You MUST use the exact Projected Forward EPS, Forward PE Multiple, Target Price, Expected Upside/Downside, and Investment Rating provided in the 'RECOMMENDED VALUATION MODEL DATA' section of the stock data context.
   - Do NOT compute different numbers, do NOT show self-questioning or calculations recalculation, and do NOT change the investment rating.
   - Describe the Forward PE model qualitatively and explain why the sector warrants this valuation (e.g., market pricing in premium growth due to high capacity expansion and AI/HPC supply constraints).

4. Volume, Shares Outstanding, and Market Cap:
   Use the provided 'Shares Outstanding' and 'Market Capitalization' from the context. Do NOT guess or hallucinate these values.
   Additionally, convert 'shares' (股) to 'Lots' (張) by dividing by 1,000 (e.g., 180,000 shares is 180 Lots) when writing about trading volume and institutional flows, and evaluate its scale relative to the daily trading volume. Use 'lots' (張) or 'shares' (股) consistently.

5. Industry Value Chain & Peer Analysis:
   You MUST include a dedicated '### 🌐 產業上下游與同業分析' section in the report.
   - Copy the exact growth metrics comparison table provided in the 'TPEX VALUE CHAIN INFORMATION' section of the stock data context.
   - Based on the provided TPEx context, analyze the target stock's position in the supply chain (e.g., Upstream/Midstream/Downstream) and discuss its competitive advantages or gaps relative to its direct domestic and foreign peers.

6. Evidence Strength & Claim Categorization (Evidence Leveling):
   For every qualitative or forward-looking claim in the report, distinguish its evidence level:
   - CONFIRMED / REPORTED: Facts directly sourced from company filings or news.
   - INFERRED: Logical industry/supply chain deductions. Mark these as Potential/Inferred (推估/潛在), and do not list specific customers/suppliers unless directly backed by facts.
   - SPECULATIVE: Subjective projections (e.g. margin forecasts).
   - **STRICT PROHIBITION ON FABRICATED PERCENTAGES**: You are STRICTLY FORBIDDEN from guessing or outputting any specific percentage metrics (e.g., <5%, 15-20%) unless they are directly provided in the stock data context. Instead, use professional qualitative phrasing (e.g., "實質營收貢獻預期有限，具體比重仍待良率與量產放量規模確認").
   - **NO AUTO-COMPLETED CLIENTS/SUPPLIERS**: You are STRICTLY FORBIDDEN from guessing or outputting upstream chip suppliers (e.g., TSMC, Intel, GlobalFoundries, Broadcom, Marvell) or downstream cloud customers (Nvidia, Microsoft, Google, Meta) unless the stock data context explicitly confirms the direct relationship. Otherwise, use "已切入北美 AI 供應鏈" or "潛在上游/推估合作夥伴".
   - **NO NARRATIVE MATCHING**: Do not describe the company as upgrading from 800G to 1.6T if its product strategy is to directly bypass 800G and enter 1.6T/3.2T.
"""
    
    user_prompt = f"""Please analyze the following data for Taiwan stock symbol {resolved_symbol} and generate the professional research report.

{data_summary}
"""
    
    # 5. Call LLM API (Custom Gateway / LiteLLM vs. Native Gemini)
    api_base = os.getenv("LLM_API_BASE")
    try:
        import requests
        url = f"{api_base.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": DEFAULT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }
        logging.info(f"Invoking LiteLLM via API Gateway: {url}")
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        report_content = response.json()["choices"][0]["message"]["content"]



        
        # 6. Parse Recommendation & Summary from YAML Frontmatter
        recommendation = "HOLD"
        summary_text = "No summary generated."
        
        # Parse recommendation
        rec_match = re.search(r"recommendation:\s*[\"']?([A-Z\s]+)[\"']?", report_content, re.I)
        if rec_match:
            recommendation = rec_match.group(1).strip().upper()
            
        # Parse summary
        sum_match = re.search(r"summary:\s*[\"']?([^\n\"']+)[\"']?", report_content)
        if sum_match:
            summary_text = sum_match.group(1).strip()
            
        # Ensure reports directory exists
        os.makedirs(REPORTS_DIR, exist_ok=True)
        
        # Save to file
        date_str = datetime.now().strftime("%Y%m%d")
        report_filename = f"{clean_sym}_{date_str}.md"
        report_filepath = os.path.join(REPORTS_DIR, report_filename)
        
        with open(report_filepath, "w", encoding="utf-8") as f:
            f.write(report_content)
            
        logging.info(f"Report saved to {report_filepath}")
        
        # 7. Record in SQLite Database
        title = f"{company_name} ({clean_sym}) Investment Report - {datetime.now().strftime('%Y-%m-%d')}"
        database.add_report(
            symbol=clean_sym,
            title=title,
            overall_score=float(score_details["total_score"]),
            recommendation=recommendation,
            file_path=report_filepath,
            summary=summary_text,
            db_path=db_path
        )
        
        return report_filepath
        
    except Exception as e:
        logging.error(f"Failed to generate report for {clean_sym}: {str(e)}")
        raise e
