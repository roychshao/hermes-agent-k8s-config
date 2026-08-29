import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from data import yfinance_client, finmind_client

# Predefined watch list of major liquid Taiwanese stocks across core sectors
DEFAULT_UNIVERSE = [
    # Semiconductors
    "2330", "2303", "2454", "3711", "2379", "3034", "5347",
    # AI / Hardware / Cooling
    "2317", "2382", "3231", "6669", "2356", "2301", "2376", "2377", "3017", "3324", "3013", "8210",
    # Electric / PCB / Networks
    "2308", "2327", "2345", "3008",
    # Shipping / Airlines
    "2603", "2609", "2618",
    # Financials
    "2881", "2882", "2886", "2891", "2884", "2885",
    # Top ETFs
    "0050", "0056", "00878", "00919", "00929"
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def score_stock(symbol: str, stock_names: dict = None) -> dict:
    """
    Computes multi-factor score (0-100) for a single Taiwan stock.
    - Institutional Buying (籌碼面): Max 35 points
    - Monthly Revenue YoY (基本面): Max 35 points
    - Technical Momentum (技術面): Max 30 points
    """
    if stock_names is None:
        stock_names = {}
    try:
        # 1. Fetch Technical Indicators (yfinance) - also contains latest price
        tech_data = yfinance_client.get_technical_indicators(symbol)
        
        current_price = tech_data.get("price", 0.0)
        if current_price == 0.0:
            try:
                price_info = yfinance_client.get_realtime_price(symbol)
                current_price = price_info.get("price", 0.0)
            except Exception:
                pass
        name = stock_names.get(symbol, symbol)
        
        ma20 = tech_data.get("ma20", 0.0)
        ma60 = tech_data.get("ma60", 0.0)
        
        tech_score = 0
        if current_price > ma20 and current_price > ma60:
            tech_score = 30
        elif current_price > ma20:
            tech_score = 15
            
        # 2. Fetch Monthly Revenue (FinMind)
        rev_records = finmind_client.get_monthly_revenue(symbol, months_back=1)
        rev_score = 0
        latest_yoy = 0.0
        
        if rev_records:
            latest_yoy = rev_records[-1]["yoy"]
            if latest_yoy > 20.0:
                rev_score = 35
            elif latest_yoy > 10.0:
                rev_score = 25
            elif latest_yoy > 0.0:
                rev_score = 15
                
        # 3. Fetch Institutional Trading (FinMind)
        inst_records = finmind_client.get_institutional_trading(symbol, days_back=5)
        inst_score = 0
        net_buy_sum = 0
        consecutive_buy_days = 0
        
        if inst_records:
            # Sum foreign & investment trust net shares
            # FinMind returns daily records; let's verify trends
            # Daily total net buy for the last 5 trading days
            daily_nets = []
            for rec in inst_records:
                net = rec["foreign_net_shares"] + rec["trust_net_shares"]
                daily_nets.append(net)
                
            net_buy_sum = sum(daily_nets)
            
            if net_buy_sum > 0:
                inst_score = 15  # Base score for net positive buy
                
                # Check consecutive buy days starting from latest day backwards
                for net in reversed(daily_nets):
                    if net > 0:
                        consecutive_buy_days += 1
                    else:
                        break
                inst_score += min(20, consecutive_buy_days * 4)  # Max +20 for consecutive buys
                
        total_score = tech_score + rev_score + inst_score
        
        return {
            "symbol": symbol,
            "name": name,
            "price": current_price,
            "tech_score": tech_score,
            "rev_score": rev_score,
            "inst_score": inst_score,
            "total_score": total_score,
            "latest_yoy": latest_yoy,
            "inst_net_5d_shares": net_buy_sum,
            "ma20": ma20,
            "ma60": ma60,
            "status": "SUCCESS"
        }
        
    except Exception as e:
        logging.error(f"Error scoring stock {symbol}: {str(e)}")
        return {
            "symbol": symbol,
            "name": "Unknown",
            "price": 0.0,
            "tech_score": 0,
            "rev_score": 0,
            "inst_score": 0,
            "total_score": 0,
            "latest_yoy": 0.0,
            "inst_net_5d_shares": 0,
            "ma20": 0.0,
            "ma60": 0.0,
            "status": f"FAILED: {str(e)}"
        }

def fetch_top_active_tickers(limit: int = 100) -> list[str]:
    """
    Fetches the top N most active Taiwan stock tickers from the TWSE Daily quotes API
    by trading value (成交金額) descending. Returns standard 4-digit common stock ids.
    """
    import requests
    from datetime import datetime, timedelta
    
    # Loop backwards up to 10 days to find the latest active trading day
    for i in range(10):
        dt = datetime.now() - timedelta(days=i)
        date_str = dt.strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={date_str}&type=ALLBUT0999"
        try:
            logging.info(f"Checking TWSE data for active trading day: {date_str}...")
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            if data.get("stat") != "OK" or not data.get("tables"):
                continue
                
            table = next((t for t in data.get("tables", []) if t.get("title") and "每日收盤行情" in t.get("title")), None)
            if not table or not table.get("data"):
                continue
                
            stocks = []
            for row in table.get("data", []):
                sid = row[0].strip()
                if len(sid) == 4 and sid.isdigit():
                    val_str = row[4].replace(",", "")
                    try:
                        val = int(val_str)
                        stocks.append((sid, val))
                    except ValueError:
                        continue
            if not stocks:
                continue
                
            stocks.sort(key=lambda x: x[1], reverse=True)
            top_stocks = [s[0] for s in stocks[:limit]]
            logging.info(f"Successfully retrieved top {len(top_stocks)} active stocks for date {date_str}.")
            return top_stocks
        except Exception as e:
            logging.warning(f"Error checking TWSE date {date_str}: {e}")
            continue
            
    logging.warning("Failed to retrieve active stocks from TWSE API. Falling back to default watch list.")
    return []

def run_screener(universe: list[str] = None) -> list[dict]:
    """
    Runs the multi-factor screener concurrently over a list of symbols,
    or triggers a highly optimized batch full-market scan if universe is ["ALL"],
    or dynamically fetches the top N active stocks if universe is ["TOP100"] or ["TOP150"].
    """
    if universe == ["ALL"] or universe == ["all"]:
        return run_full_market_screener()
        
    if not universe:
        universe = ["TOP100"]
        
    if universe and len(universe) == 1 and str(universe[0]).upper().startswith("TOP"):
        limit_str = str(universe[0]).upper().replace("TOP", "")
        try:
            limit = int(limit_str)
        except ValueError:
            limit = 100
            
        logging.info(f"Fetching top {limit} active stocks from TWSE by trading value...")
        top_tickers = fetch_top_active_tickers(limit=limit)
        if top_tickers:
            universe = top_tickers
        else:
            universe = DEFAULT_UNIVERSE
            
    targets = universe if universe else DEFAULT_UNIVERSE

    # Fetch stock names mapping to avoid slow yfinance info calls
    stock_names = {}
    try:
        from data.finmind_client import get_data_loader
        dl = get_data_loader()
        df_info = dl.taiwan_stock_info()
        stock_names = dict(zip(df_info["stock_id"], df_info["stock_name"]))
    except Exception as e:
        logging.warning(f"Failed to fetch stock names from FinMind: {e}")

    results = []
    
    logging.info(f"Running multi-factor screener over {len(targets)} symbols...")
    
    # Use ThreadPoolExecutor to speed up API IO fetches
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(score_stock, sym, stock_names): sym for sym in targets}
        
        for fut in as_completed(futures):
            res = fut.result()
            if res["status"] == "SUCCESS":
                results.append(res)
                
    # Sort results by total score descending
    results.sort(key=lambda x: x["total_score"], reverse=True)
    logging.info(f"Screener complete. Found {len(results)} valid scored targets.")
    return results

def run_full_market_screener() -> list[dict]:
    """
    Runs a highly optimized batch full-market scan of all active Taiwan common stocks.
    Requires a paid/sponsor FinMind API Token for bulk downloading monthly revenue
    and institutional investor datasets.
    """
    import os
    import pandas as pd
    import yfinance as yf
    from datetime import datetime, timedelta
    from FinMind.data import DataLoader
    
    logging.info("Starting full-market batch screening...")
    
    # 1. Initialize FinMind DataLoader
    token = os.getenv("FINMIND_API_TOKEN")
    dl = DataLoader(token=token) if token else DataLoader()
    
    # 2. Fetch all active stock metadata
    try:
        df_info = dl.taiwan_stock_info()
        # Filter for standard 4-digit common stocks (exclude warrants, indices, etc.)
        df_info = df_info[df_info["stock_id"].str.len() == 4]
        # Exclude stocks without industry category
        df_info = df_info[df_info["industry_category"] != ""]
        # Keep list and tpex normal stocks
        df_info = df_info[df_info["type"].isin(["twse", "tpex"])]
        active_stocks = df_info.to_dict("records")
        stock_ids = [s["stock_id"] for s in active_stocks]
        stock_names = {s["stock_id"]: s["stock_name"] for s in active_stocks}
        logging.info(f"Retrieved {len(stock_ids)} active Taiwan common stocks from metadata.")
    except Exception as e:
        logging.error(f"Failed to fetch stock metadata: {e}")
        return []
        
    # 3. Batch download prices and technical indicators from yfinance
    tickers = []
    ticker_to_sid = {}
    for s in active_stocks:
        sid = s["stock_id"]
        suffix = ".TW" if s["type"] == "twse" else ".TWO"
        ticker = f"{sid}{suffix}"
        tickers.append(ticker)
        ticker_to_sid[ticker] = sid
        
    logging.info(f"Downloading historical daily prices for {len(tickers)} tickers from yfinance...")
    try:
        # Download 90 days of daily data in a single batch request
        df_prices = yf.download(tickers, period="90d", interval="1d", group_by="ticker", threads=True, progress=False)
    except Exception as e:
        logging.error(f"Failed to download prices from yfinance: {e}")
        return []
        
    # 4. Fetch monthly revenue and institutional trades in batch from FinMind
    df_rev = pd.DataFrame()
    df_inst = pd.DataFrame()
    is_paid_user = True
    
    try:
        # Monthly revenue starting from 14 months ago to compute YoY
        start_date_rev = (datetime.now() - timedelta(days=450)).strftime("%Y-%m-%d")
        logging.info("Attempting batch download of monthly revenue from FinMind...")
        df_rev = dl.taiwan_stock_month_revenue(start_date=start_date_rev)
    except Exception as e:
        if "Your level is free" in str(e):
            is_paid_user = False
            logging.warning("Your FinMind token is at the FREE tier, which does not support full-market batch queries.")
        else:
            logging.error(f"Failed to download monthly revenue: {e}")
            return []
            
    if is_paid_user:
        try:
            # Institutional trades starting from 15 days ago
            start_date_inst = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
            logging.info("Attempting batch download of institutional trading data from FinMind...")
            df_inst = dl.taiwan_stock_institutional_investors(start_date=start_date_inst)
        except Exception as e:
            logging.error(f"Failed to download institutional trading data: {e}")
            return []
            
    # Fallback to standard watch list if level is free
    if not is_paid_user:
        logging.info("Reverting to the default watch list screener due to account level restrictions.")
        return run_screener(universe=DEFAULT_UNIVERSE)

        
    # 5. Process and score in memory
    logging.info("Processing full-market metrics in memory...")
    results = []
    
    # Pre-process monthly revenue YoY in pandas
    df_rev = df_rev.sort_values(["stock_id", "date"]).reset_index(drop=True)
    df_rev["revenue_year"] = df_rev["revenue_year"].astype(int)
    df_rev["revenue_month"] = df_rev["revenue_month"].astype(int)
    df_rev["revenue"] = df_rev["revenue"].astype(float)
    
    df_rev_prev = df_rev.copy()
    df_rev_prev["revenue_year"] = df_rev_prev["revenue_year"] + 1
    df_rev_prev = df_rev_prev.rename(columns={"revenue": "prev_revenue"})
    
    df_rev_yoy = pd.merge(
        df_rev,
        df_rev_prev[["stock_id", "revenue_year", "revenue_month", "prev_revenue"]],
        on=["stock_id", "revenue_year", "revenue_month"],
        how="left"
    )
    df_rev_yoy["yoy"] = 0.0
    valid_prev = (df_rev_yoy["prev_revenue"] > 0)
    df_rev_yoy.loc[valid_prev, "yoy"] = ((df_rev_yoy["revenue"] - df_rev_yoy["prev_revenue"]) / df_rev_yoy["prev_revenue"]) * 100
    
    df_latest_rev = df_rev_yoy.groupby("stock_id").last().reset_index()
    latest_rev_map = df_latest_rev.set_index("stock_id")[["yoy"]].to_dict("index")
    
    # Pre-process institutional trading
    df_inst["net_buy"] = df_inst["buy"] - df_inst["sell"]
    df_inst_filtered = df_inst[df_inst["name"].isin(["Foreign_Investor", "Investment_Trust"])]
    df_inst_daily = df_inst_filtered.groupby(["stock_id", "date"])["net_buy"].sum().reset_index()
    df_inst_daily = df_inst_daily.sort_values(["stock_id", "date"]).reset_index(drop=True)
    
    inst_daily_map = {}
    for sid, group in df_inst_daily.groupby("stock_id"):
        daily_nets = group["net_buy"].tolist()[-5:]
        inst_daily_map[sid] = daily_nets
        
    # 6. Loop over all stocks and calculate scores
    for ticker in tickers:
        sid = ticker_to_sid[ticker]
        name = stock_names.get(sid, "Unknown")
        
        try:
            if ticker not in df_prices.columns.levels[0]:
                continue
                
            ticker_df = df_prices[ticker].dropna()
            if len(ticker_df) < 60:
                continue
                
            current_price = float(ticker_df["Close"].iloc[-1])
            ma20 = float(ticker_df["Close"].rolling(window=20).mean().iloc[-1])
            ma60 = float(ticker_df["Close"].rolling(window=60).mean().iloc[-1])
            
            # Technical Score
            tech_score = 0
            if current_price > ma20 and current_price > ma60:
                tech_score = 30
            elif current_price > ma20:
                tech_score = 15
                
            # Revenue Score
            rev_score = 0
            latest_yoy = 0.0
            if sid in latest_rev_map:
                latest_yoy = latest_rev_map[sid]["yoy"]
                if latest_yoy > 20.0:
                    rev_score = 35
                elif latest_yoy > 10.0:
                    rev_score = 25
                elif latest_yoy > 0.0:
                    rev_score = 15
                    
            # Institutional Score
            inst_score = 0
            net_buy_sum = 0
            if sid in inst_daily_map:
                daily_nets = inst_daily_map[sid]
                net_buy_sum = sum(daily_nets)
                if net_buy_sum > 0:
                    inst_score = 15
                    consecutive_buy_days = 0
                    for net in reversed(daily_nets):
                        if net > 0:
                            consecutive_buy_days += 1
                        else:
                            break
                    inst_score += min(20, consecutive_buy_days * 4)
                    
            total_score = tech_score + rev_score + inst_score
            
            results.append({
                "symbol": sid,
                "name": name,
                "price": current_price,
                "tech_score": tech_score,
                "rev_score": rev_score,
                "inst_score": inst_score,
                "total_score": total_score,
                "latest_yoy": latest_yoy,
                "inst_net_5d_shares": net_buy_sum,
                "ma20": ma20,
                "ma60": ma60,
                "status": "SUCCESS"
            })
        except Exception:
            continue
            
    # Sort results
    results.sort(key=lambda x: x["total_score"], reverse=True)
    logging.info(f"Full-market batch screening complete. Scored {len(results)} stocks successfully.")
    return results

def analyze_news_sentiment(symbols: list[str]) -> list[dict]:
    """
    Scores the given stocks, fetches their recent news, calls the LLM (Gemini)
    to evaluate sentiment and summarize, and logs the decisions to the database.
    """
    import os
    import requests
    import json
    from datetime import datetime
    from db import database
    
    # 1. Fetch stock names
    stock_names = {}
    try:
        from data.finmind_client import get_data_loader
        dl = get_data_loader()
        df_info = dl.taiwan_stock_info()
        stock_names = dict(zip(df_info["stock_id"], df_info["stock_name"]))
    except Exception as e:
        logging.warning(f"Failed to fetch stock names from FinMind: {e}")

    # 2. Score stocks and fetch news
    payloads = []
    for sym in symbols:
        try:
            score_data = score_stock(sym, stock_names)
            if score_data["status"] != "SUCCESS":
                continue
                
            from data import finmind_client
            news_records = finmind_client.get_stock_news(sym, days_back=3)
            headlines = [n["title"] for n in news_records[:10]]
            
            payloads.append({
                "score_data": score_data,
                "headlines": headlines
            })
        except Exception as e:
            logging.error(f"Error processing {sym} for news analysis: {e}")
            
    if not payloads:
        return []
        
    api_base = os.getenv("LLM_API_BASE")
    api_key = os.getenv("LITE_LLM_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
    model = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    
    if not api_base or not api_key:
        raise ValueError("LLM_API_BASE and LLM_API_KEY must be set in environment.")
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    url = f"{api_base.rstrip('/')}/chat/completions"
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    results = []
    for item in payloads:
        sd = item["score_data"]
        sym = sd["symbol"]
        name = sd["name"]
        headlines = item["headlines"]
        
        sentiment = "NEUTRAL"
        summary = "No recent news found."
        
        if headlines:
            headlines_str = "\n".join(f"- {h}" for h in headlines)
            system_prompt = (
                "You are an expert financial analyst. Analyze the provided stock news headlines "
                "and determine the overall market sentiment for this stock. "
                "Output exactly a JSON object with two keys:\\n"
                "1. 'sentiment': Must be either 'BULLISH', 'NEUTRAL', or 'BEARISH'\\n"
                "2. 'summary': A concise one-sentence Chinese summary of the news.\\n"
                "Output ONLY valid raw JSON without markdown code blocks."
            )
            user_prompt = f"Stock: {sym} ({name})\\nRecent News:\\n{headlines_str}"
            
            try:
                r = requests.post(url, headers=headers, json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.1
                }, timeout=15)
                
                if r.status_code == 200:
                    text = r.json()["choices"][0]["message"]["content"].strip()
                    if text.startswith("```"):
                        text = text.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
                        if text.startswith("json"):
                            text = text.split("\n", 1)[1].strip()
                    res_json = json.loads(text)
                    sentiment = res_json.get("sentiment", "NEUTRAL").upper()
                    summary = res_json.get("summary", "")
            except Exception as e:
                logging.error(f"Failed to analyze news for {sym} via LLM: {e}")
                
        selected = (sentiment == "BULLISH" and sd["total_score"] >= 60)
        
        try:
            database.init_db()
            database.save_agent_decision(
                date=date_str,
                symbol=sym,
                name=name,
                price=sd["price"],
                tech_score=sd["tech_score"],
                rev_score=sd["rev_score"],
                inst_score=sd["inst_score"],
                total_score=sd["total_score"],
                news_sentiment=sentiment,
                news_summary=summary,
                selected_for_research=selected
            )
        except Exception as e:
            logging.error(f"Failed to save decision for {sym} to database: {e}")
            
        results.append({
            "date": date_str,
            "symbol": sym,
            "name": name,
            "price": sd["price"],
            "total_score": sd["total_score"],
            "tech_score": sd["tech_score"],
            "rev_score": sd["rev_score"],
            "inst_score": sd["inst_score"],
            "news_sentiment": sentiment,
            "news_summary": summary,
            "selected_for_research": selected
        })
        
    return results

