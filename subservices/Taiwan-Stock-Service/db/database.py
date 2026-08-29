import os
import sqlite3
from datetime import datetime
from typing import Optional

DEFAULT_DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "portfolio.db"))

def get_db_type() -> str:
    """Returns the configured database type: 'postgres' or 'sqlite' (default)."""
    return os.getenv("DB_TYPE", "sqlite").lower()

def get_connection(db_path=DEFAULT_DB_PATH):
    """Establishes connection to either SQLite or PostgreSQL database."""
    db_type = get_db_type()
    
    if db_type == "postgres":
        import psycopg2
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "portfolio"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres")
        )
    else:
        # Ensure directory exists for SQLite
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

def get_cursor(conn):
    """Returns a cursor compatible with dict-like row access for both SQLite and PostgreSQL."""
    db_type = get_db_type()
    if db_type == "postgres":
        import psycopg2.extras
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        return conn.cursor()

def format_query(query: str) -> str:
    """Formats SQL query placeholders (replaces ? with %s for PostgreSQL)."""
    if get_db_type() == "postgres":
        return query.replace("?", "%s")
    return query

def get_id_type() -> str:
    """Returns the autoincrement primary key column type for table creation."""
    if get_db_type() == "postgres":
        return "SERIAL PRIMARY KEY"
    return "INTEGER PRIMARY KEY AUTOINCREMENT"

def init_db(db_path=DEFAULT_DB_PATH):
    """Initializes the database schema if tables do not exist."""
    conn = get_connection(db_path)
    cursor = get_cursor(conn)
    id_type = get_id_type()
    
    # Transactions table
    cursor.execute(format_query(f"""
    CREATE TABLE IF NOT EXISTS transactions (
        id {id_type},
        symbol TEXT NOT NULL,
        name TEXT NOT NULL,
        trade_type TEXT NOT NULL CHECK(trade_type IN ('BUY', 'SELL')),
        quantity INTEGER NOT NULL CHECK(quantity > 0),
        price REAL NOT NULL CHECK(price > 0),
        fee REAL NOT NULL CHECK(fee >= 0),
        tax REAL NOT NULL CHECK(tax >= 0),
        total_amount REAL NOT NULL, -- Total cash spent (BUY) or received (SELL)
        timestamp TEXT NOT NULL,
        notes TEXT
    )
    """))
    
    # Portfolio table (aggregated positions)
    cursor.execute(format_query("""
    CREATE TABLE IF NOT EXISTS portfolio (
        symbol TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        total_quantity INTEGER NOT NULL CHECK(total_quantity >= 0),
        avg_cost REAL NOT NULL CHECK(avg_cost >= 0),
        realized_pnl REAL NOT NULL DEFAULT 0.0
    )
    """))
    
    # Reports index table
    cursor.execute(format_query(f"""
    CREATE TABLE IF NOT EXISTS reports (
        id {id_type},
        symbol TEXT NOT NULL,
        title TEXT NOT NULL,
        overall_score REAL,
        recommendation TEXT NOT NULL,
        file_path TEXT NOT NULL,
        summary TEXT,
        created_at TEXT NOT NULL
    )
    """))
    
    # Agent Decisions table for tracking recommendations and sentiment
    cursor.execute(format_query(f"""
    CREATE TABLE IF NOT EXISTS agent_decisions (
        id {id_type},
        date TEXT NOT NULL,
        symbol TEXT NOT NULL,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        tech_score INTEGER NOT NULL,
        rev_score INTEGER NOT NULL,
        inst_score INTEGER NOT NULL,
        total_score INTEGER NOT NULL,
        news_sentiment TEXT,
        news_summary TEXT,
        selected_for_research BOOLEAN NOT NULL,
        created_at TEXT NOT NULL
    )
    """))
    
    # Stock Value Chains cache table
    cursor.execute(format_query("""
    CREATE TABLE IF NOT EXISTS stock_value_chains (
        symbol TEXT PRIMARY KEY,
        industry_code TEXT,
        industry_name TEXT,
        subcategory_code TEXT,
        subcategory_name TEXT,
        peers_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """))
    
    conn.commit()
    conn.close()

def is_etf(symbol: str) -> bool:
    """
    Determines if a Taiwan stock symbol is an ETF or ETN to apply correct tax rate.
    ETFs in Taiwan typically start with '00', '03', '07', or '08'.
    """
    clean_sym = symbol.strip().split(".")[0]
    return clean_sym.startswith("00") or clean_sym.startswith("03") or clean_sym.startswith("07") or clean_sym.startswith("08")

def calculate_costs(symbol: str, trade_type: str, quantity: int, price: float, discount_rate: float = 0.6) -> tuple[float, float, float]:
    """
    Calculates brokerage fees and transaction taxes for Taiwan stock market.
    - Brokerage Fee: 0.1425% of trading volume, subject to broker discount. Minimum 20 NTD.
    - Transaction Tax: 0.3% when selling stocks, 0.1% when selling ETFs. None when buying.
    """
    volume = quantity * price
    
    # Brokerage fee (applied to both buy and sell)
    raw_fee = volume * 0.001425 * discount_rate
    fee = float(max(20.0, round(raw_fee)))
    
    # Transaction tax (applied only to sells)
    tax = 0.0
    if trade_type == "SELL":
        tax_rate = 0.001 if is_etf(symbol) else 0.003
        tax = float(round(volume * tax_rate))
        
    if trade_type == "BUY":
        total_amount = volume + fee  # BUY costs cash
    else:
        total_amount = volume - fee - tax  # SELL nets cash
        
    return fee, tax, total_amount

def add_transaction(symbol: str, name: str, trade_type: str, quantity: int, price: float, 
                    discount_rate: float = 0.6, notes: str = None, timestamp: str = None, 
                    db_path=DEFAULT_DB_PATH) -> dict:
    """
    Records a trade transaction and updates the portfolio position using weighted-average cost.
    """
    trade_type = trade_type.upper()
    if trade_type not in ("BUY", "SELL"):
        raise ValueError("trade_type must be either 'BUY' or 'SELL'")
        
    if quantity <= 0:
        raise ValueError("Quantity must be greater than 0")
        
    if price <= 0:
        raise ValueError("Price must be greater than 0")
        
    fee, tax, total_amount = calculate_costs(symbol, trade_type, quantity, price, discount_rate)
    trade_time = timestamp if timestamp else datetime.now().isoformat()
    
    conn = get_connection(db_path)
    cursor = get_cursor(conn)
    
    try:
        # Check current position
        cursor.execute(format_query("SELECT total_quantity, avg_cost, realized_pnl FROM portfolio WHERE symbol = ?"), (symbol,))
        row = cursor.fetchone()
        
        current_qty = row["total_quantity"] if row else 0
        current_avg_cost = row["avg_cost"] if row else 0.0
        current_realized_pnl = row["realized_pnl"] if row else 0.0
        
        if trade_type == "SELL" and current_qty < quantity:
            raise ValueError(f"Insufficient position to sell. Current: {current_qty}, Request: {quantity}")
            
        # Write transaction log
        cursor.execute(format_query("""
            INSERT INTO transactions (symbol, name, trade_type, quantity, price, fee, tax, total_amount, timestamp, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """), (symbol, name, trade_type, quantity, price, fee, tax, total_amount, trade_time, notes))
        
        # Calculate new position metrics
        if trade_type == "BUY":
            new_qty = current_qty + quantity
            new_avg_cost = ((current_qty * current_avg_cost) + total_amount) / new_qty
            new_realized_pnl = current_realized_pnl
        else:  # SELL
            new_qty = current_qty - quantity
            new_avg_cost = current_avg_cost if new_qty > 0 else 0.0
            
            # Realized PnL = Cash Net Received - (Quantity Sold * Avg Cost)
            realized_pnl_change = total_amount - (quantity * current_avg_cost)
            new_realized_pnl = current_realized_pnl + realized_pnl_change
            
        # Update or insert into portfolio
        if row:
            cursor.execute(format_query("""
                UPDATE portfolio 
                SET total_quantity = ?, avg_cost = ?, realized_pnl = ?
                WHERE symbol = ?
            """), (new_qty, new_avg_cost, new_realized_pnl, symbol))
        else:
            cursor.execute(format_query("""
                INSERT INTO portfolio (symbol, name, total_quantity, avg_cost, realized_pnl)
                VALUES (?, ?, ?, ?, ?)
            """), (symbol, name, new_qty, new_avg_cost, new_realized_pnl))
            
        conn.commit()
        
        return {
            "symbol": symbol,
            "name": name,
            "trade_type": trade_type,
            "quantity": quantity,
            "price": price,
            "fee": fee,
            "tax": tax,
            "total_amount": total_amount,
            "new_quantity": new_qty,
            "new_avg_cost": new_avg_cost,
            "realized_pnl": new_realized_pnl
        }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_portfolio(db_path=DEFAULT_DB_PATH) -> list[dict]:
    """Retrieves all active holding positions with PnL summary."""
    conn = get_connection(db_path)
    cursor = get_cursor(conn)
    cursor.execute(format_query("SELECT * FROM portfolio ORDER BY symbol ASC"))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_transactions(symbol: str = None, db_path=DEFAULT_DB_PATH) -> list[dict]:
    """Retrieves list of all transactions, optionally filtered by stock symbol."""
    conn = get_connection(db_path)
    cursor = get_cursor(conn)
    if symbol:
        cursor.execute(format_query("SELECT * FROM transactions WHERE symbol = ? ORDER BY timestamp DESC"), (symbol,))
    else:
        cursor.execute(format_query("SELECT * FROM transactions ORDER BY timestamp DESC"))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_report(symbol: str, title: str, overall_score: float, recommendation: str, 
               file_path: str, summary: str = None, db_path=DEFAULT_DB_PATH):
    """Indexes a generated research report."""
    conn = get_connection(db_path)
    cursor = get_cursor(conn)
    created_at = datetime.now().isoformat()
    cursor.execute(format_query("""
        INSERT INTO reports (symbol, title, overall_score, recommendation, file_path, summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """), (symbol, title, overall_score, recommendation.upper(), file_path, summary, created_at))
    conn.commit()
    conn.close()

def get_reports(symbol: str = None, db_path=DEFAULT_DB_PATH) -> list[dict]:
    """Retrieves indexed research reports."""
    conn = get_connection(db_path)
    cursor = get_cursor(conn)
    if symbol:
        cursor.execute(format_query("SELECT * FROM reports WHERE symbol = ? ORDER BY created_at DESC"), (symbol,))
    else:
        cursor.execute(format_query("SELECT * FROM reports ORDER BY created_at DESC"))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_agent_decision(date: str, symbol: str, name: str, price: float,
                         tech_score: int, rev_score: int, inst_score: int, total_score: int,
                         news_sentiment: str, news_summary: str, selected_for_research: bool,
                         db_path=DEFAULT_DB_PATH):
    """Saves a stock selection and sentiment decision record by the agent."""
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = get_cursor(conn)
    created_at = datetime.now().isoformat()
    try:
        cursor.execute(format_query("""
            INSERT INTO agent_decisions (date, symbol, name, price, tech_score, rev_score, inst_score, total_score,
                                        news_sentiment, news_summary, selected_for_research, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """), (date, symbol, name, price, tech_score, rev_score, inst_score, total_score,
               news_sentiment, news_summary, selected_for_research, created_at))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_agent_decisions_by_days(days: int = 7, db_path=DEFAULT_DB_PATH) -> list[dict]:
    """Retrieves historical stock recommendations and sentiment decisions from the last N days."""
    from datetime import datetime, timedelta
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = get_cursor(conn)
    threshold_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        cursor.execute(format_query("""
            SELECT * FROM agent_decisions 
            WHERE date >= ? 
            ORDER BY date DESC, total_score DESC
        """), (threshold_date,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def save_value_chain_cache(symbol: str, industry_code: str, industry_name: str, subcategory_code: str, subcategory_name: str, peers_json: str, db_path=DEFAULT_DB_PATH):
    """Saves or updates a stock's TPEx value chain mapping cache."""
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = get_cursor(conn)
    from datetime import datetime
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute(format_query("""
            INSERT OR REPLACE INTO stock_value_chains (symbol, industry_code, industry_name, subcategory_code, subcategory_name, peers_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """), (symbol, industry_code, industry_name, subcategory_code, subcategory_name, peers_json, updated_at))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_value_chain_cache(symbol: str, db_path=DEFAULT_DB_PATH) -> Optional[dict]:
    """Retrieves cached TPEx value chain mapping for a stock. Returns None if no cache or expired (>7 days)."""
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = get_cursor(conn)
    from datetime import datetime, timedelta
    try:
        cursor.execute(format_query("""
            SELECT * FROM stock_value_chains WHERE symbol = ?
        """), (symbol,))
        row = cursor.fetchone()
        if not row:
            return None
        
        row_dict = dict(row)
        # Verify 7-day expiration
        updated_at = datetime.strptime(row_dict["updated_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() - updated_at > timedelta(days=7):
            return None # Expired
            
        return row_dict
    finally:
        conn.close()
