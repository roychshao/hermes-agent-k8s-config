import yfinance as yf
import pandas as pd
from functools import lru_cache

@lru_cache(maxsize=256)
def resolve_ticker(symbol: str) -> tuple[yf.Ticker, str]:
    """
    Resolves standard Taiwan stock symbol (e.g., '2330') to yfinance Ticker.
    Tries '.TW' (Listed) first, then falls back to '.TWO' (OTC).
    """
    clean_sym = symbol.strip().upper()
    if clean_sym.endswith(".TW") or clean_sym.endswith(".TWO"):
        return yf.Ticker(clean_sym), clean_sym
    
    # Try Listed (.TW)
    tw_symbol = f"{clean_sym}.TW"
    ticker = yf.Ticker(tw_symbol)
    try:
        # Fetching last_price or market_cap to verify ticker validity
        if ticker.fast_info is not None and ticker.fast_info.last_price > 0:
            return ticker, tw_symbol
    except Exception:
        pass
        
    # Fallback to OTC (.TWO)
    two_symbol = f"{clean_sym}.TWO"
    ticker = yf.Ticker(two_symbol)
    return ticker, two_symbol

def get_realtime_price(symbol: str) -> dict:
    """
    Fetches real-time price metrics and current-day stats for a stock symbol.
    """
    ticker, resolved_sym = resolve_ticker(symbol)
    
    try:
        fast_info = ticker.fast_info
        last_price = fast_info.last_price
        
        # Pulling details from history to guarantee current day data
        hist = ticker.history(period="1d")
        if hist.empty:
            raise ValueError(f"No pricing history found for symbol: {symbol}")
            
        open_price = float(hist["Open"].iloc[0])
        high_price = float(hist["High"].iloc[0])
        low_price = float(hist["Low"].iloc[0])
        volume = int(hist["Volume"].iloc[0])
        prev_close = float(fast_info.previous_close if fast_info.previous_close else open_price)
        
        change = last_price - prev_close
        change_pct = (change / prev_close) * 100 if prev_close > 0 else 0.0
        
        # Get company name
        # info is a slow request, fallback to ticker symbol if it fails or is slow
        name = ticker.info.get("longName", resolved_sym) if hasattr(ticker, "info") else resolved_sym
        
        try:
            shares = int(fast_info.shares) if hasattr(fast_info, "shares") and fast_info.shares else 0
        except (TypeError, ValueError):
            shares = 0
        market_cap = last_price * shares if shares > 0 else 0
        
        return {
            "symbol": symbol,
            "resolved_symbol": resolved_sym,
            "name": name,
            "price": float(last_price),
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "prev_close": prev_close,
            "volume": volume,
            "change": float(change),
            "change_pct": float(change_pct),
            "shares": int(shares),
            "market_cap": float(market_cap)
        }
    except Exception as e:
        raise RuntimeError(f"Failed to fetch yfinance data for {symbol}: {str(e)}")

def get_technical_indicators(symbol: str, days: int = 120) -> dict:
    """
    Fetches historical adjusted close prices and computes 20MA and 60MA.
    Also returns current position relative to these averages.
    """
    ticker, resolved_sym = resolve_ticker(symbol)
    
    try:
        # Fetch historical data using period
        hist = ticker.history(period=f"{days}d")
        if len(hist) < 60:
            # Try fetching a larger window or default to actual history length
            hist = ticker.history(period="1y")
            
        if hist.empty or len(hist) < 20:
            return {
                "price": 0.0,
                "ma20": 0.0,
                "ma60": 0.0,
                "above_ma20": False,
                "above_ma60": False,
                "error": "Insufficient history to calculate indicators"
            }
            
        # Using adjusted Close prices (yf.Ticker.history returns adjusted Close by default)
        close_prices = hist["Close"]
        current_price = float(close_prices.iloc[-1])
        
        ma20 = float(close_prices.rolling(window=20).mean().iloc[-1])
        ma60 = float(close_prices.rolling(window=60).mean().iloc[-1]) if len(close_prices) >= 60 else ma20
        
        return {
            "price": current_price,
            "ma20": ma20,
            "ma60": ma60,
            "above_ma20": current_price > ma20,
            "above_ma60": current_price > ma60
        }
    except Exception as e:
        return {
            "price": 0.0,
            "ma20": 0.0,
            "ma60": 0.0,
            "above_ma20": False,
            "above_ma60": False,
            "error": str(e)
        }
