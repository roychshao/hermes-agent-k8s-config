import sys
import argparse
import os
from datetime import datetime
from db import database
from data import yfinance_client
from core import screener, researcher

def print_table(headers: list[str], rows: list[list]):
    """Helper function to print formatted terminal tables."""
    if not rows:
        print("No records found.")
        return
        
    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            widths[idx] = max(widths[idx], len(str(val)))
            
    # Print headers
    header_str = " | ".join(f"{str(h):<{widths[idx]}}" for idx, h in enumerate(headers))
    print(header_str)
    print("-" * (sum(widths) + 3 * (len(headers) - 1)))
    
    # Print rows
    for row in rows:
        row_str = " | ".join(f"{str(val):<{widths[idx]}}" for idx, val in enumerate(row))
        print(row_str)

def cmd_price(args):
    print(f"Fetching real-time data for {args.symbol}...")
    try:
        data = yfinance_client.get_realtime_price(args.symbol)
        tech = yfinance_client.get_technical_indicators(args.symbol)
        
        headers = ["Field", "Value"]
        rows = [
            ["Symbol", data["resolved_symbol"]],
            ["Name", data["name"]],
            ["Price (TWD)", f"{data['price']:.2f}"],
            ["Change", f"{data['change']:.2f} ({data['change_pct']:.2f}%)"],
            ["Open / Prev Close", f"{data['open']:.2f} / {data['prev_close']:.2f}"],
            ["High / Low", f"{data['high']:.2f} / {data['low']:.2f}"],
            ["Volume", f"{data['volume']:,}"],
            ["MA20 / MA60", f"{tech.get('ma20', 0):.2f} / {tech.get('ma60', 0):.2f}"],
            ["MA Trend", "Bullish (Above 20MA/60MA)" if tech.get("above_ma20") and tech.get("above_ma60") else "Neutral/Bearish"]
        ]
        print_table(headers, rows)
    except Exception as e:
        print(f"Error fetching price: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_screen(args):
    print("Running stock screener (might take a moment to fetch market data)...")
    try:
        symbols = None
        if args.symbols:
            if args.symbols.strip().lower() == "all":
                symbols = ["ALL"]
            else:
                symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        results = screener.run_screener(universe=symbols)


        headers = ["Rank", "Symbol", "Name", "Price", "Score", "Tech", "Rev", "Inst", "Rev YoY", "Status"]
        rows = []
        for idx, r in enumerate(results):
            rows.append([
                idx + 1,
                r["symbol"],
                r["name"],
                f"{r['price']:.2f}",
                r["total_score"],
                r["tech_score"],
                r["rev_score"],
                r["inst_score"],
                f"{r['latest_yoy']:.1f}%",
                r["status"]
            ])
        print_table(headers, rows)
    except Exception as e:
        print(f"Screener failed: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_research(args):
    print(f"Running deep research and generating report for {args.symbol}...")
    try:
        report_path = researcher.generate_report(args.symbol)
        print("\n" + "="*50)
        print("RESEARCH COMPLETED SUCCESSFULLY!")
        print(f"Report File: {report_path}")
        print("="*50)
        
        # Display the report preview (frontmatter and summary)
        with open(report_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        frontmatter = []
        in_fm = False
        for line in lines:
            if line.strip() == "---":
                if not in_fm:
                    in_fm = True
                    continue
                else:
                    break
            if in_fm:
                frontmatter.append(line.strip())
                
        print("\nReport Metadata Preview:")
        for fm in frontmatter:
            print(f"  {fm}")
            
    except Exception as e:
        print(f"Research failed: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_trade(args):
    print(f"Recording transaction: {args.trade_type} {args.quantity} shares of {args.symbol} at {args.price} TWD...")
    try:
        # Resolve company name from yfinance
        price_info = yfinance_client.get_realtime_price(args.symbol)
        name = price_info["name"]
        
        res = database.add_transaction(
            symbol=args.symbol,
            name=name,
            trade_type=args.trade_type,
            quantity=args.quantity,
            price=args.price,
            discount_rate=args.discount,
            notes=args.notes
        )
        
        print("\nTransaction Recorded Successfully!")
        headers = ["Metric", "Value"]
        rows = [
            ["Symbol/Name", f"{res['symbol']} ({res['name']})"],
            ["Trade Type", res["trade_type"]],
            ["Price / Qty", f"{res['price']} TWD / {res['quantity']} shares"],
            ["Brokerage Fee", f"{res['fee']} TWD"],
            ["Transaction Tax", f"{res['tax']} TWD"],
            ["Total Cash Amount", f"{res['total_amount']:.2f} TWD"],
            ["New Net Position", f"{res['new_quantity']} shares"],
            ["New Avg Cost", f"{res['new_avg_cost']:.2f} TWD"],
            ["Cumulative Realized PnL", f"{res['realized_pnl']:.2f} TWD"]
        ]
        print_table(headers, rows)
        
    except Exception as e:
        print(f"Failed to record trade: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_portfolio(args):
    print("Fetching portfolio holdings and calculating real-time PnL...")
    try:
        database.init_db()
        holdings = database.get_portfolio()
        
        headers = ["Symbol", "Name", "Qty", "Avg Cost", "Current Price", "Market Value", "Unrealized PnL", "Realized PnL"]
        rows = []
        
        total_market_val = 0.0
        total_unrealized_pnl = 0.0
        total_realized_pnl = 0.0
        
        for h in holdings:
            symbol = h["symbol"]
            qty = h["total_quantity"]
            avg_cost = h["avg_cost"]
            realized_pnl = h["realized_pnl"]
            total_realized_pnl += realized_pnl
            
            if qty > 0:
                # Fetch current price dynamically
                try:
                    price_info = yfinance_client.get_realtime_price(symbol)
                    curr_price = price_info["price"]
                except Exception:
                    curr_price = avg_cost  # Fallback to cost if API fails
                    
                market_val = qty * curr_price
                unrealized_pnl = market_val - (qty * avg_cost)
                
                total_market_val += market_val
                total_unrealized_pnl += unrealized_pnl
                
                rows.append([
                    symbol,
                    h["name"],
                    f"{qty:,}",
                    f"{avg_cost:.2f}",
                    f"{curr_price:.2f}",
                    f"{market_val:,.2f}",
                    f"{unrealized_pnl:+,.2f}",
                    f"{realized_pnl:+,.2f}"
                ])
            else:
                # Stock sold out but has historical realized PnL
                rows.append([
                    symbol,
                    h["name"],
                    "0",
                    "0.00",
                    "0.00",
                    "0.00",
                    "0.00",
                    f"{realized_pnl:+,.2f}"
                ])
                
        print_table(headers, rows)
        print("\n" + "="*50)
        print(f"Total Market Value:  {total_market_val:,.2f} TWD")
        print(f"Total Unrealized PnL: {total_unrealized_pnl:+,.2f} TWD")
        print(f"Total Realized PnL:   {total_realized_pnl:+,.2f} TWD")
        print("="*50)
        
    except Exception as e:
        print(f"Failed to fetch portfolio: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_analyze(args):
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("Error: No symbols provided.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Analyzing news sentiment and scoring for: {', '.join(symbols)}...")
    try:
        results = screener.analyze_news_sentiment(symbols)
        if not results:
            print("No valid stock data was processed.")
            return
            
        print("\nAnalysis & Decision Results:")
        headers = ["Date", "Symbol", "Name", "Price", "Score", "Sentiment", "Selected?", "Summary"]
        rows = []
        for r in results:
            rows.append([
                r["date"],
                r["symbol"],
                r["name"],
                f"{r['price']:.2f}",
                r["total_score"],
                r["news_sentiment"],
                "YES" if r["selected_for_research"] else "NO",
                r["news_summary"]
            ])
        print_table(headers, rows)
    except Exception as e:
        print(f"Failed to analyze news: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_recommendations(args):
    print(f"Fetching agent stock recommendations from the last {args.days} days...")
    try:
        recs = database.get_agent_decisions_by_days(days=args.days)
        headers = ["Date", "Symbol", "Name", "Price", "Score", "Sentiment", "Selected?", "Summary"]
        rows = []
        for r in recs:
            rows.append([
                r["date"],
                r["symbol"],
                r["name"],
                f"{r['price']:.2f}",
                r["total_score"],
                r["news_sentiment"] or "N/A",
                "YES" if r["selected_for_research"] else "NO",
                r["news_summary"] or "N/A"
            ])
        print_table(headers, rows)
    except Exception as e:
        print(f"Failed to fetch recommendations: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_digest(args):
    print("Running Daily stock screener and deep research digest synthesis...")
    try:
        from core.daily_digest import DailyDigestPipeline
        pipeline = DailyDigestPipeline()
        report_path = pipeline.run_pipeline()
        if report_path:
            print("\n" + "="*50)
            print("DAILY DIGEST COMPLETED SUCCESSFULLY!")
            print(f"Report File: {report_path}")
            print("="*50)
        else:
            print("No daily digest report could be generated.")
    except Exception as e:
        print(f"Failed to generate daily digest: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Taiwan Stock Research Agent - CLI Interface")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # price subcommand
    p_parser = subparsers.add_parser("price", help="Fetch real-time stock price and indicators")
    p_parser.add_argument("symbol", type=str, help="Taiwan stock symbol (e.g. 2330)")
    
    # screen subcommand
    s_parser = subparsers.add_parser("screen", help="Run multi-factor stock screener")
    s_parser.add_argument("--symbols", type=str, default=None, help="Comma-separated Taiwan stock tickers to scan (e.g. 2330,2317)")

    
    # research subcommand
    r_parser = subparsers.add_parser("research", help="Run deep research and write a report")
    r_parser.add_argument("symbol", type=str, help="Taiwan stock symbol (e.g. 3017)")
    
    # trade subcommand
    t_parser = subparsers.add_parser("trade", help="Record a stock transaction")
    t_parser.add_argument("symbol", type=str, help="Stock symbol")
    t_parser.add_argument("trade_type", type=str, choices=["BUY", "SELL", "buy", "sell"], help="Transaction type")
    t_parser.add_argument("quantity", type=int, help="Shares count")
    t_parser.add_argument("price", type=float, help="Execution price per share")
    t_parser.add_argument("--discount", type=float, default=0.6, help="Brokerage fee discount (default: 0.6)")
    t_parser.add_argument("--notes", type=str, default=None, help="Additional notes")
    
    # portfolio subcommand
    subparsers.add_parser("portfolio", help="Show current portfolio and real-time PnL")
    
    # analyze-news subcommand
    an_parser = subparsers.add_parser("analyze-news", help="Analyze news sentiment and record selection decisions")
    an_parser.add_argument("symbols", type=str, help="Comma-separated Taiwan stock symbols to analyze (e.g. 2330,3017)")
    
    # recommendations subcommand
    rec_parser = subparsers.add_parser("recommendations", help="Query past agent decisions by days")
    rec_parser.add_argument("--days", type=int, default=7, help="Number of past days to query (default: 7)")
    
    # digest subcommand
    subparsers.add_parser("digest", help="Generate Daily Stock Screener and Research Digest by running screen, research, and synthesis")
    
    args = parser.parse_args()
    
    if args.command == "price":
        cmd_price(args)
    elif args.command == "screen":
        cmd_screen(args)
    elif args.command == "research":
        cmd_research(args)
    elif args.command == "trade":
        args.trade_type = args.trade_type.upper()
        cmd_trade(args)
    elif args.command == "portfolio":
        cmd_portfolio(args)
    elif args.command == "analyze-news":
        cmd_analyze(args)
    elif args.command == "recommendations":
        cmd_recommendations(args)
    elif args.command == "digest":
        cmd_digest(args)

if __name__ == "__main__":
    main()
