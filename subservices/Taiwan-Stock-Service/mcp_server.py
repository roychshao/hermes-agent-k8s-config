import logging
import re
from fastmcp import FastMCP


from db import database
from data import yfinance_client
from core import screener, researcher

# Initialize FastMCP Server
mcp = FastMCP("Taiwan Stock Research Agent")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

@mcp.tool()
def get_price(symbol: str) -> str:
    """
    Fetches real-time price, day statistics, and technical moving averages for a Taiwan stock symbol (e.g. '2330', '3017').
    """
    try:
        data = yfinance_client.get_realtime_price(symbol)
        tech = yfinance_client.get_technical_indicators(symbol)
        
        above_ma = "Above 20MA and 60MA (Bullish)" if tech.get("above_ma20") and tech.get("above_ma60") else "Below moving averages (Bearish/Neutral)"
        
        output = f"""=== Real-time Stock Data: {data['name']} ({data['resolved_symbol']}) ===
Current Price: {data['price']} TWD
Price Change: {data['change']} TWD ({data['change_pct']:.2f}%)
Daily Open / Prev Close: {data['open']} / {data['prev_close']} TWD
Daily High / Low: {data['high']} / {data['low']} TWD
Volume: {data['volume']:,} shares
Technical moving averages:
- MA20: {tech.get('ma20', 0):.2f}
- MA60: {tech.get('ma60', 0):.2f}
- Trend: {above_ma}
"""
        return output
    except Exception as e:
        return f"Error fetching price for {symbol}: {str(e)}"

@mcp.tool()
def run_stock_screener(symbols: list[str] = None) -> str:
    """
    Runs the multi-factor Taiwan stock screener (analyzing institutional buying, revenue YoY, and moving averages)
    and returns a ranked list of high-potential targets.
    Arguments:
    - symbols: Optional list of Taiwan stock tickers to scan (e.g. ['2330', '2317']). If not provided, defaults to a watch list of 39 liquid blue-chips.
    """
    try:
        results = screener.run_screener(universe=symbols)

        if not results:
            return "Screener completed, but no stocks matched the required filters."
            
        output = "=== Multi-Factor Taiwan Stock Screen Results ===\n"
        output += f"{'Rank':<5} | {'Symbol':<8} | {'Name':<12} | {'Price':<8} | {'Score':<5} | {'Tech':<4} | {'Rev':<4} | {'Inst':<4} | {'Revenue YoY':<11}\n"
        output += "-" * 90 + "\n"
        
        for idx, r in enumerate(results):
            output += f"{idx+1:<5} | {r['symbol']:<8} | {r['name']:<12} | {r['price']:<8.2f} | {r['total_score']:<5} | {r['tech_score']:<4} | {r['rev_score']:<4} | {r['inst_score']:<4} | {r['latest_yoy']:<10.1f}%\n"
            
        return output
    except Exception as e:
        return f"Error running screener: {str(e)}"

@mcp.tool()
def generate_research_report(symbol: str) -> str:
    """
    Generates a deep-dive research report for a Taiwan stock symbol, incorporating financials,
    institutional flow trends, recent news, and whitelisted web search supply chain details.
    """
    try:
        report_path = researcher.generate_report(symbol)
        
        # Read the full report content to return directly as a response
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        return f"""=== Research Report Generated Successfully! ===
File Path on Server: {report_path}

{content}
"""
    except Exception as e:
        return f"Error generating research report for {symbol}: {str(e)}"


@mcp.tool()
def record_transaction(symbol: str, trade_type: str, quantity: int, price: float, notes: str = None) -> str:
    """
    Records a stock purchase or sale transaction in the portfolio database and computes PnL.
    Arguments:
    - trade_type: Must be either 'BUY' or 'SELL'
    - quantity: Share count (must be positive)
    - price: Executed price per share in TWD
    - notes: Optional notes or details about the transaction
    """
    try:
        # Resolve company name
        price_info = yfinance_client.get_realtime_price(symbol)
        name = price_info["name"]
        
        res = database.add_transaction(
            symbol=symbol,
            name=name,
            trade_type=trade_type,
            quantity=quantity,
            price=price,
            discount_rate=0.6,
            notes=notes
        )
        
        output = f"""=== Transaction Recorded Successfully ===
Symbol/Name: {res['symbol']} ({res['name']})
Action: {res['trade_type']}
Shares: {res['quantity']} shares @ {res['price']} TWD
Fees: {res['fee']} TWD (Tax: {res['tax']} TWD)
Total Cash flow: {res['total_amount']:.2f} TWD
--- Current Position Status ---
Total quantity: {res['new_quantity']} shares
Weighted Average Cost: {res['new_avg_cost']:.2f} TWD
Realized PnL: {res['realized_pnl']:.2f} TWD
"""
        return output
    except Exception as e:
        return f"Error recording transaction for {symbol}: {str(e)}"

@mcp.tool()
def get_portfolio_holdings() -> str:
    """
    Retrieves all current stock holdings and calculates real-time unrealized PnL based on current market prices.
    """
    try:
        database.init_db()
        holdings = database.get_portfolio()
        if not holdings:
            return "No assets in the portfolio."
            
        output = "=== Real-Time Portfolio Holdings & PnL ===\n"
        output += f"{'Symbol':<8} | {'Name':<12} | {'Qty':<10} | {'Avg Cost':<10} | {'Current Price':<13} | {'Market Value':<14} | {'Unrealized PnL':<15} | {'Realized PnL':<12}\n"
        output += "-" * 115 + "\n"
        
        total_market_val = 0.0
        total_unrealized_pnl = 0.0
        total_realized_pnl = 0.0
        
        for h in holdings:
            sym = h["symbol"]
            qty = h["total_quantity"]
            avg_cost = h["avg_cost"]
            realized_pnl = h["realized_pnl"]
            total_realized_pnl += realized_pnl
            
            if qty > 0:
                try:
                    price_info = yfinance_client.get_realtime_price(sym)
                    curr_price = price_info["price"]
                except Exception:
                    curr_price = avg_cost
                    
                market_val = qty * curr_price
                unrealized_pnl = market_val - (qty * avg_cost)
                
                total_market_val += market_val
                total_unrealized_pnl += unrealized_pnl
                
                output += f"{sym:<8} | {h['name']:<12} | {qty:<10,} | {avg_cost:<10.2f} | {curr_price:<13.2f} | {market_val:<14,.2f} | {unrealized_pnl:<+15,.2f} | {realized_pnl:<+12,.2f}\n"
            else:
                # Fully sold out position with historical realized PnL
                output += f"{sym:<8} | {h['name']:<12} | {'0':<10} | {'0.00':<10} | {'0.00':<13} | {'0.00':<14} | {'0.00':<15} | {realized_pnl:<+12,.2f}\n"
                
        output += "=" * 115 + "\n"
        output += f"Total Market Value:  {total_market_val:,.2f} TWD\n"
        output += f"Total Unrealized PnL: {total_unrealized_pnl:+,.2f} TWD\n"
        output += f"Total Realized PnL:   {total_realized_pnl:+,.2f} TWD\n"
        return output
    except Exception as e:
        return f"Error fetching portfolio holdings: {str(e)}"

@mcp.tool()
def analyze_stock_news(symbols: str) -> str:
    """
    Analyzes news sentiment for a list of comma-separated stock symbols (e.g. '2330,3017').
    Scores the stock, fetches the last 3 days of news, runs LLM analysis, and automatically
    saves the decision record to the PostgreSQL database.
    """
    try:
        sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
        if not sym_list:
            return "Error: No symbols provided."
            
        results = screener.analyze_news_sentiment(sym_list)
        if not results:
            return "No valid stock data was analyzed."
            
        output = "=== News Sentiment & Selection Results ===\n"
        output += f"{'Date':<10} | {'Symbol':<8} | {'Name':<12} | {'Price':<8} | {'Score':<5} | {'Sentiment':<10} | {'Selected?':<9} | {'Summary'}\n"
        output += "-" * 110 + "\n"
        for r in results:
            sel_str = "YES" if r["selected_for_research"] else "NO"
            output += f"{r['date']:<10} | {r['symbol']:<8} | {r['name']:<12} | {r['price']:<8.2f} | {r['total_score']:<5} | {r['news_sentiment']:<10} | {sel_str:<9} | {r['news_summary']}\n"
            
        return output
    except Exception as e:
        return f"Error analyzing news: {str(e)}"

@mcp.tool()
def get_agent_recommendations(days: int = 7) -> str:
    """
    Retrieves the history of stock recommendations and sentiment decisions made by the agent over the last N days.
    """
    try:
        recs = database.get_agent_decisions_by_days(days=days)
        if not recs:
            return f"No recommendations found in the last {days} days."
            
        output = f"=== Agent Recommendations (Last {days} Days) ===\n"
        output += f"{'Date':<10} | {'Symbol':<8} | {'Name':<12} | {'Price':<8} | {'Score':<5} | {'Sentiment':<10} | {'Selected?':<9} | {'Summary'}\n"
        output += "-" * 110 + "\n"
        for r in recs:
            sel_str = "YES" if r["selected_for_research"] else "NO"
            output += f"{r['date']:<10} | {r['symbol']:<8} | {r['name']:<12} | {r['price']:<8.2f} | {r['total_score']:<5} | {r['news_sentiment']:<10} | {sel_str:<9} | {r['news_summary']}\n"
            
        return output
    except Exception as e:
        return f"Error retrieving recommendations: {str(e)}"


@mcp.tool()
def generate_daily_digest() -> str:
    """
    Automatically screens Taiwan stocks, generates deep research reports for the top 10 stocks concurrently,
    and synthesizes a consolidated Daily Stock Screener and Research Digest Markdown report.
    """
    try:
        from core.daily_digest import DailyDigestPipeline
        pipeline = DailyDigestPipeline()
        report_path = pipeline.run_pipeline()
        if report_path:
            with open(report_path, "r", encoding="utf-8") as f:
                content = f.read()
            return f"=== Daily Digest Generated Successfully! ===\nFile Path: {report_path}\n\n{content}"
        else:
            return "No daily digest report could be generated."
    except Exception as e:
        return f"Error generating daily digest: {str(e)}"


if __name__ == "__main__":
    import os
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    host = os.getenv("MCP_HOST", "0.0.0.0")
    logging.info(f"Starting FastMCP server with transport: {transport} on host: {host}")
    if transport in {"sse", "http", "streamable-http"}:
        mcp.run(transport=transport, host=host)
    else:
        mcp.run(transport=transport)


