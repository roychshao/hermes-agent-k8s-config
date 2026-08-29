# Taiwan Stock Research Agent (台股輔助選股助手)

This project is a high-performance Python application designed to assist in screening, researching, and recording transactions of Taiwanese stocks (台股). It is optimized for integration with agentic frameworks (like Hermes) via both a Command Line Interface (CLI) and a Model Context Protocol (MCP) server.

---

## Features

1.  **Real-Time Price Queries**: Fetches real-time price info, day metrics, and technical indicators (20MA, 60MA using adjusted close prices) via yfinance. Automatically resolves listed (`.TW`) and OTC (`.TWO`) symbols.
2.  **Multi-Factor Screener**: Scores liquid Taiwanese stocks based on combined weights:
    *   *籌碼面 (Institutional Flows)*: Combined net buy trends of Foreign Investors and Investment Trusts over the last 5 days.
    *   *基本面 (Fundamentals)*: Latest monthly revenue YoY growth (%).
    *   *技術面 (Technical)*: Location relative to 20MA and 60MA.
3.  **Dynamic Industry Research Reports**: Generates professional buy-side research reports. Fetches FinMind stock news, pulls quarterly EPS/Margins, and runs whitelisted search queries to extract industry chain and supply chain advantages, utilizing the Gemini API.
4.  **Portfolio Trade & PnL Bookkeeper**: Records BUY/SELL trades in an SQLite database. Features weighted-average cost accounting and calculates Taiwan transaction fees (brokerage fee with discount, min 20 NTD) and stock transaction tax (0.3% for common stocks, 0.1% for ETFs).
5.  **MCP Server & CLI Dual Interface**: Operates via terminal commands or exposes native tools to AI agents using FastMCP.
6.  **Code Quality & Coverage (SonarQube)**: Configured with automated unit tests and Docker-based SonarQube integration.

---

## Directory Structure

```text
stock-research-agent/
├── db/
│   └── database.py           # SQLite manager (portfolio accounting & report cataloging)
├── data/
│   ├── finmind_client.py     # FinMind API (revenue YoY, EPS, news, institutions)
│   ├── yfinance_client.py    # yfinance client (real-time & MA indicators)
│   └── search_client.py      # Google News RSS parser with whitelisting and denoising
├── core/
│   ├── screener.py           # Multi-factor Taiwan stock screener
│   └── researcher.py         # Report engine invoking LLM (Gemini)
├── reports/                  # Generated research reports (*.md)
├── tests/                    # Comprehensive unit tests (100% mocked)
├── cli.py                    # Command Line Interface (CLI) entry point
├── mcp_server.py             # Model Context Protocol (MCP) server entry point
├── pyproject.toml            # Project dependencies and configurations (managed via uv)
├── sonar-project.properties  # SonarQube project analysis configuration
├── docker-compose.sonar.yml  # Docker Compose file for local SonarQube server
└── run_sonar_analysis.sh     # Script to run unit tests and trigger SonarQube scan
```

---

## Installation & Setup

We manage dependencies using the ultra-fast Python package manager **`uv`**.

1.  **Clone the Repository** (or work in the local folder).
2.  **Set up Environment Variables**:
    Create a `.env` file at the root of the project:
    ```env
    FINMIND_API_TOKEN=your_finmind_token_here (optional, free/guest fallback is automatic)
    GEMINI_API_KEY=your_gemini_api_key_here
    GEMINI_MODEL=gemini-1.5-flash
    ```
3.  **Install dependencies**:
    `uv` will automatically manage your virtual environment and dependencies:
    ```bash
    uv sync
    ```

---

## Command Line Interface (CLI) Usage

Use `uv run cli.py <command>` to run the CLI tools:

### 1. Fetch Real-time Stock Price & Trends
```bash
uv run cli.py price 2330
```

### 2. Run the Multi-Factor Screener
```bash
uv run cli.py screen
```

### 3. Generate a Deep Research Report
Generates a structured buy-side report in `reports/` and indexes it in the database.
```bash
uv run cli.py research 3017
```

### 4. Record a Transaction
Records a BUY or SELL, computes brokerage fees ( Taiwan standard fee: 0.1425%, min 20 NTD, custom discount) and sell taxes (0.3% for stocks, 0.1% for ETFs).
```bash
uv run cli.py trade 2330 BUY 1000 100.0 --discount 0.6 --notes "First tranche"
uv run cli.py trade 2330 SELL 500 120.0 --discount 0.6
```

### 5. Check Portfolio Holdings & PnL
Calculates real-time unrealized PnL dynamically based on the latest stock price.
```bash
uv run cli.py portfolio
```

---

## Exposing Tools via MCP Server

Expose these tools directly to your AI Agent (like Hermes) using stdio:
```bash
uv run mcp_server.py
```
Tools exposed:
*   `get_price(symbol)`
*   `run_stock_screener()`
*   `generate_research_report(symbol)`
*   `record_transaction(symbol, trade_type, quantity, price, notes)`
*   `get_portfolio_holdings()`

---

## Quality Assurance & SonarQube

### 1. Run Unit Tests & Coverage
To run the mock-based unit tests and view the coverage report:
```bash
PYTHONPATH=. uv run pytest --cov --cov-report=term-missing
```

### 2. Run SonarQube Analysis
We provide a shell script that runs your tests, generates the XML coverage file, boots up a local SonarQube server in Docker (on port 9000), and performs a full analysis scan:
```bash
./run_sonar_analysis.sh
```
Once complete, open http://localhost:9000 in your browser to inspect bugs, code smells, vulnerabilities, and test coverage graphs.
