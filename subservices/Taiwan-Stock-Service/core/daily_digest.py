import os
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests

from core import screener, researcher
from db import database

logger = logging.getLogger(__name__)

DEFAULT_DIGEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "reports", "daily_digest"))

class DailyDigestPipeline:
    """
    Orchestrates the Daily Stock Screener & Research Digest generation.
    """
    def __init__(self, digest_dir: str = DEFAULT_DIGEST_DIR, db_path: str = None):
        self.digest_dir = digest_dir
        self.db_path = db_path or database.DEFAULT_DB_PATH
        database.init_db(self.db_path)

    def run_pipeline(self, universe: List[str] = None) -> Optional[str]:
        """
        Executes the daily digest generation workflow:
        1. Auto screen stocks (using screener.run_screener).
        2. Get top 10 stocks by total score.
        3. Run research on these 10 stocks concurrently.
        4. Synthesize the research reports into a single daily digest report.
        5. Save the digest report.
        """
        logger.info("Starting Daily Screener & Research Digest Pipeline...")
        
        # Step 1: Run Screener
        scored_stocks = self.run_screener(universe)
        if not scored_stocks:
            logger.warning("No scored stocks found from screener. Daily digest skipped.")
            return None
            
        # Step 2: Select top 10 stocks
        top_stocks = self.select_top_stocks(scored_stocks, limit=10)
        if not top_stocks:
            logger.warning("No top stocks selected. Daily digest skipped.")
            return None
            
        # Step 3: Run research on these 10 stocks
        reports_data = self.generate_research_reports(top_stocks)
        if not reports_data:
            logger.warning("No research reports generated. Daily digest skipped.")
            return None
            
        # Step 4: Synthesize consolidated daily digest
        report_md = self.synthesize_daily_digest(reports_data)
        
        # Step 5: Save report to disk
        saved_path = self.save_report(report_md)
        return saved_path

    def run_screener(self, universe: List[str] = None) -> List[Dict[str, Any]]:
        """Runs the multi-factor stock screener to retrieve scored stocks."""
        logger.info("Running stock screener...")
        return screener.run_screener(universe=universe)

    def select_top_stocks(self, scored_stocks: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
        """Selects the top N scored stocks."""
        top_stocks = scored_stocks[:limit]
        logger.info(f"Selected top {len(top_stocks)} stocks for research: {[s['symbol'] for s in top_stocks]}")
        return top_stocks

    def generate_research_reports(self, top_stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generates research reports for top stocks in parallel."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        reports_data = []
        logger.info(f"Generating research reports concurrently for {len(top_stocks)} stocks...")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(researcher.generate_report, stock["symbol"], self.db_path): stock 
                for stock in top_stocks
            }
            
            for fut in as_completed(futures):
                stock = futures[fut]
                symbol = stock["symbol"]
                try:
                    report_path = fut.result()
                    if report_path and os.path.exists(report_path):
                        with open(report_path, "r", encoding="utf-8") as f:
                            report_content = f.read()
                        
                        reports_data.append({
                            "symbol": symbol,
                            "name": stock.get("name", "Unknown"),
                            "score_data": stock,
                            "report_path": report_path,
                            "report_content": report_content
                        })
                        logger.info(f"Successfully generated research report for {symbol}.")
                    else:
                        logger.error(f"Report path for {symbol} is invalid or empty.")
                except Exception as e:
                    logger.error(f"Failed to generate research report for {symbol}: {e}")
                    
        # Sort the results to maintain the order of the top_stocks
        symbol_order = {s["symbol"]: idx for idx, s in enumerate(top_stocks)}
        reports_data.sort(key=lambda x: symbol_order.get(x["symbol"], 999))
        return reports_data

    def synthesize_daily_digest(self, reports_data: List[Dict[str, Any]]) -> str:
        """Invokes LLM to aggregate and synthesize the top 10 stock research reports into a consolidated daily digest."""
        now = datetime.now()
        current_date_str = now.strftime("%Y年%m月%d日")
        current_year = now.year
        
        system_prompt = f"""You are a Senior Buy-side Equity Research Analyst.
The current date of report generation is {current_date_str}. The current year is {current_year}.
Any financial projections or timing projections must be relative to {current_year} (e.g. Q4 {current_year} is immediate, {current_year + 1} is mid-term).

You are synthesizing a Daily Stock Screener & Research Digest. You have been provided with individual research reports and quantitative screening data for the top 10 Taiwan stocks.

You must adhere to the following rules:
1. NUMERICAL & ENTITY CONSISTENCY:
   - NEVER fabricate, guess, or change the stock ticker, company name, stock price, recommendation, or quant scores. Use the exact values provided in the input context.
2. NO NARRATIVE MATCHING or FABRICATION:
   - Base your synthesis strictly on the provided research reports. Do not introduce external facts or guess suppliers/customers unless explicitly confirmed in the provided text.
3. STRICT PROHIBITION ON FABRICATED METRICS:
   - Do not invent or guess any target prices, PE multiples, or growth rates. Use exactly what is written in the source reports.
4. PROFESSIONAL FORMAT:
   - Use clean Markdown and write in Traditional Chinese.

Structure your report with the following main sections:
# 📅 每日個股篩選與研究彙整報告 (Daily Stock Screener & Research Digest)
**報告日期**：{current_date_str}

## 📊 今日強勢股篩選總覽 (Screener Overview Table)
[Provide a Markdown table showing: Rank, Stock Ticker & Name, Price, Total Score, Recommendation, and Summary. List all analyzed stocks in order.]

## 🌐 產業與板塊核心動態 (Market & Sector Analysis)
[Provide a synthesis of the common themes, industries, or sectors represented by these top stocks. Discuss what secular trends (e.g., AI server expansion, semiconductor node migrations, shipping cycle) are driving the high scores today based on the reports.]

## 🔍 個股研究摘要 (Individual Stock Highlights)
[For each stock, provide a comprehensive, detailed, and structured research summary based on the provided report. Avoid brief one-sentence bullet points. You must summarize the report in depth, detailing the positive news/catalysts, supply chain status, competitive peer comparison, future opportunities, and valuation. Use the following sub-headers for each stock:

### [Rank]. [Symbol] [Company Name]
* **推薦評等與量化得分**：[Recommendation] (整體評分 [Total Score]/100, 技術: [Tech Score], 營收: [Rev Score], 籌碼: [Inst Score])
* **投資評等與摘要**：[A detailed paragraph summarizing the investment rating and core thesis from the report]

#### 💡 推薦理由與核心利多 (Investment Thesis & Positive Catalysts)
- [Detail the exact reasons why this stock is recommended, including any specific positive news, operational breakthroughs, new product lines, capacity expansions, or other growth catalysts mentioned in the report. Cite specific details and timing projections.]

#### 🌐 供應鏈狀況與競爭格局 (Supply Chain & Competitive Landscape)
- [Describe the company's position in the industry value chain (e.g. upstream cooling components, packaging substrate, foundry etc.).]
- [Detail the upstream/downstream client-supplier dynamics, and specify peer competitors comparison data, including metrics from the peer table (like Revenue YoY, EPS, Operating Margin Growth) if present.]

#### 🔮 未來增長機會與關鍵展望 (Future Opportunities & Outlook)
- [Summarize the short-term and mid-term growth drivers, market demands, or key strategic directions the company is pursuing as highlighted in the report.]

#### 📈 估值模型與目標價 (Valuation & Target Price)
- [Provide the detailed PE Valuation Model parameters: Current Price, Projected Forward EPS, Forward PE Multiple, Target Price, and Expected Upside/Downside.]
]

## 🎯 投資觀點與綜合支持
[High-conviction general conclusion and actionable insights based on the screen and research results.]
"""

        formatted_input = []
        for idx, r in enumerate(reports_data):
            formatted_input.append(f"""
=== STOCK #{idx+1}: {r['symbol']} {r['name']} ===
Score Data: {json.dumps(r['score_data'], ensure_ascii=False)}
Research Report:
{r['report_content']}
=======================================
""")
        user_prompt = "\n".join(formatted_input)
        
        report_content = self._call_llm(system_prompt, user_prompt)
        
        if not report_content:
            logger.warning("LLM digest synthesis failed. Generating fallback report...")
            report_content = f"# 📅 每日個股篩選與研究彙整報告 (Daily Stock Screener & Research Digest)\n\n"
            report_content += f"**報告日期**: {current_date_str}\n\n"
            report_content += "## 📊 今日強勢股篩選總覽 (Screener Overview Table)\n\n"
            report_content += "| 排名 | 股票代號 / 名稱 | 現行股價 | 整體評分 |\n"
            report_content += "| :---: | :--- | :---: | :---: |\n"
            for idx, r in enumerate(reports_data):
                sd = r["score_data"]
                report_content += f"| {idx+1} | {r['symbol']} {r['name']} | {sd.get('price', 0.0):.2f} TWD | {sd.get('total_score', 0)}/100 |\n"
            
            report_content += "\n## 🔍 個股研究摘要\n\n"
            for idx, r in enumerate(reports_data):
                report_content += f"### {idx+1}. {r['symbol']} {r['name']}\n"
                report_content += f"詳細研究報告已儲存至: `{r['report_path']}`\n\n"
                summary_lines = []
                for line in r['report_content'].split("\n"):
                    if not line.startswith("---") and line.strip():
                        summary_lines.append(line)
                    if len(summary_lines) >= 5:
                        break
                report_content += "\n".join(summary_lines) + "\n\n"
                
        return report_content

    def save_report(self, report_md: str) -> str:
        """Saves the generated Markdown report to the daily digest folder."""
        os.makedirs(self.digest_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        report_filename = f"digest_{date_str}.md"
        report_filepath = os.path.join(self.digest_dir, report_filename)
        
        with open(report_filepath, "w", encoding="utf-8") as f:
            f.write(report_md)
            
        logger.info(f"Daily supply chain digest saved to: {report_filepath}")
        return report_filepath

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        api_key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("AVANTE_GEMINI_API_KEY")
        api_base = os.getenv("LLM_API_BASE")
        model = os.getenv("LLM_MODEL", "gemini-1.5-flash")
        
        if not api_base:
            logger.error("LLM_API_BASE environment variable is missing.")
            return ""
        if not api_key:
            logger.error("LLM_API_KEY/GEMINI_API_KEY environment variable is missing.")
            return ""
            
        url = f"{api_base.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1
        }
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Failed to call LLM API for daily digest: {e}")
            return ""
