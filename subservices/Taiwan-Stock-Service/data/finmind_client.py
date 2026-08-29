import os
import re
import logging
from functools import lru_cache
from typing import Optional, Any
import pandas as pd
from datetime import datetime, timedelta
from FinMind.data import DataLoader
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

def get_data_loader() -> DataLoader:
    """Instantiates the FinMind DataLoader, logging in with token if available."""
    token = os.getenv("FINMIND_API_TOKEN")
    if token:
        # FinMind DataLoader can be initialized with token or you can use login method
        return DataLoader(token=token)
    return DataLoader()

def get_monthly_revenue(symbol: str, months_back: int = 15) -> list[dict]:
    """
    Fetches monthly revenue and calculates YoY growth rates.
    """
    clean_sym = symbol.strip().split(".")[0]
    dl = get_data_loader()
    
    # Calculate start date (months_back + 12 to get YoY baseline)
    start_date = (datetime.now() - timedelta(days=(months_back + 12) * 30)).strftime("%Y-%m-%d")
    
    try:
        df = dl.taiwan_stock_month_revenue(stock_id=clean_sym, start_date=start_date)
        if df.empty:
            return []
            
        # Sort by date
        df = df.sort_values("date").reset_index(drop=True)
        
        # Calculate YoY
        records = []
        for i, row in df.iterrows():
            year = int(row["revenue_year"])
            month = int(row["revenue_month"])
            rev = float(row["revenue"])
            
            # Find the same month of the previous year
            prev_year_row = df[(df["revenue_year"] == year - 1) & (df["revenue_month"] == month)]
            
            yoy = 0.0
            if not prev_year_row.empty:
                prev_rev = float(prev_year_row["revenue"].values[0])
                if prev_rev > 0:
                    yoy = ((rev - prev_rev) / prev_rev) * 100
                    
            records.append({
                "date": row["date"],
                "year": year,
                "month": month,
                "revenue": rev,
                "yoy": yoy
            })
            
        # Return only the requested number of recent months
        return records[-months_back:]
    except Exception as e:
        # Fail gracefully by returning empty or propagating
        raise RuntimeError(f"Failed to fetch monthly revenue from FinMind for {clean_sym}: {str(e)}")

def get_quarterly_financials(symbol: str, quarters_back: int = 6) -> list[dict]:
    """
    Fetches quarterly financial statements (EPS, Gross Profit Margin, Operating Margin).
    """
    clean_sym = symbol.strip().split(".")[0]
    dl = get_data_loader()
    
    start_date = (datetime.now() - timedelta(days=(quarters_back + 2) * 90)).strftime("%Y-%m-%d")
    
    try:
        df = dl.taiwan_stock_financial_statement(stock_id=clean_sym, start_date=start_date)
        if df.empty:
            return []
            
        # Pivot the financial statements to get items per date
        dates = df["date"].unique()
        records = []
        
        for dt in sorted(dates):
            sub_df = df[df["date"] == dt]
            
            # Extract values
            revenue_val = sub_df[sub_df["type"] == "Revenue"]["value"].values
            gp_val = sub_df[sub_df["type"] == "GrossProfit"]["value"].values
            op_val = sub_df[sub_df["type"] == "OperatingIncome"]["value"].values
            eps_val = sub_df[sub_df["type"] == "EPS"]["value"].values
            
            rev = float(revenue_val[0]) if len(revenue_val) > 0 else 0.0
            gp = float(gp_val[0]) if len(gp_val) > 0 else 0.0
            op = float(op_val[0]) if len(op_val) > 0 else 0.0
            eps = float(eps_val[0]) if len(eps_val) > 0 else 0.0
            
            gp_margin = (gp / rev * 100) if rev > 0 else 0.0
            op_margin = (op / rev * 100) if rev > 0 else 0.0
            
            records.append({
                "date": dt,
                "revenue": rev,
                "gross_profit_margin": gp_margin,
                "operating_margin": op_margin,
                "eps": eps
            })
            
        return records[-quarters_back:]
    except Exception as e:
        raise RuntimeError(f"Failed to fetch financials from FinMind for {clean_sym}: {str(e)}")

def get_institutional_trading(symbol: str, days_back: int = 15) -> list[dict]:
    """
    Fetches institutional buy/sell records and returns a aggregated summary of the last N days.
    """
    clean_sym = symbol.strip().split(".")[0]
    dl = get_data_loader()
    
    start_date = (datetime.now() - timedelta(days=days_back * 2)).strftime("%Y-%m-%d")
    
    try:
        df = dl.taiwan_stock_institutional_investors(stock_id=clean_sym, start_date=start_date)
        if df.empty:
            return []
            
        # Group by date and name, compute net buy
        df["net_buy"] = df["buy"] - df["sell"]
        
        # Sort by date descending
        unique_dates = sorted(df["date"].unique(), reverse=True)[:days_back]
        
        records = []
        for dt in reversed(unique_dates):
            date_df = df[df["date"] == dt]
            
            foreign_net = date_df[date_df["name"] == "Foreign_Investor"]["net_buy"].sum()
            trust_net = date_df[date_df["name"] == "Investment_Trust"]["net_buy"].sum()
            dealer_net = date_df[date_df["name"].isin(["Dealer_self", "Dealer_Hedging", "Dealer"])]["net_buy"].sum()
            
            records.append({
                "date": dt,
                "foreign_net_shares": int(foreign_net),
                "trust_net_shares": int(trust_net),
                "dealer_net_shares": int(dealer_net),
                "total_institutional_net_shares": int(foreign_net + trust_net + dealer_net)
            })
            
        return records
    except Exception as e:
        raise RuntimeError(f"Failed to fetch institutional trading from FinMind for {clean_sym}: {str(e)}")

def get_stock_news(symbol: str, days_back: int = 7) -> list[dict]:
    """
    Fetches stock-specific news from FinMind for the last N days.
    """
    clean_sym = symbol.strip().split(".")[0]
    dl = get_data_loader()
    
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    
    try:
        df = dl.taiwan_stock_news(stock_id=clean_sym, start_date=start_date)
        if df.empty:
            return []
            
        # Keep latest news first
        df = df.sort_values("date", ascending=False).reset_index(drop=True)
        
        news_list = []
        for _, row in df.iterrows():
            news_list.append({
                "date": row["date"],
                "source": row.get("source", "Unknown"),
                "title": row["title"],
                "link": row.get("link", "")
            })
        return news_list
    except Exception as e:
        # Fallback to empty news list if API fails
        return []

@lru_cache(maxsize=128)
def resolve_ticker_by_name(company_name: str) -> Optional[str]:
    """
    Look up the stock symbol (e.g. '8111') for a given Chinese company name (e.g. '立碁')
    using FinMind's TaiwanStockInfo dataset.
    """
    try:
        dl = get_data_loader()
        df = dl.taiwan_stock_info()
        if df.empty:
            return None
        # Clean company name (e.g. strip "股份", "有限公司", "控股", "科技")
        clean_name = re.sub(r"股份|有限公司|控股|科技", "", company_name).strip()
        # Find exact matches first
        exact_match = df[df["stock_name"] == clean_name]
        if not exact_match.empty:
            return str(exact_match.iloc[0]["stock_id"])
            
        # Find fuzzy matches (e.g., name contains clean_name)
        fuzzy_match = df[df["stock_name"].str.contains(clean_name, na=False)]
        if not fuzzy_match.empty:
            return str(fuzzy_match.iloc[0]["stock_id"])
    except Exception as e:
        logger.error(f"Failed to resolve ticker by name {company_name}: {e}")
    return None

@lru_cache(maxsize=128)
def get_company_name_by_ticker(symbol: str) -> Optional[str]:
    """
    Look up the company name (e.g. '立碁') for a given stock symbol (e.g. '8111')
    using FinMind's TaiwanStockInfo dataset.
    """
    try:
        clean_sym = symbol.strip().split(".")[0]
        dl = get_data_loader()
        df = dl.taiwan_stock_info()
        if df.empty:
            return None
        match = df[df["stock_id"] == clean_sym]
        if not match.empty:
            return str(match.iloc[0]["stock_name"])
    except Exception as e:
        logger.error(f"Failed to look up company name for {symbol}: {e}")
    return None
