import os
import re
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup
import urllib.parse

# Setup logging
logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HTML_PARSER = "html.parser"

class DigitimesScrapingStrategy(ABC):
    """
    Abstract Base Class representing the scraping strategy for DIGITIMES.
    Part of the Strategy Pattern.
    """
    @abstractmethod
    def fetch_article_text(self, session: requests.Session, url: str, title: str) -> str:
        """Fetches the main text of the article."""
        pass

class FreeVisitorStrategy(DigitimesScrapingStrategy):
    """
    Scraping strategy for visitors without a paid subscription.
    Fetches the public preview and supplements it with a Google News/MoneyDJ search
    to retrieve full summaries or轉載 (reprints) for free.
    """
    def fetch_article_text(self, session: requests.Session, url: str, title: str) -> str:
        text_context = ""
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        
        # 1. Fetch public preview
        try:
            r = session.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                html = r.content.decode("utf-8", errors="ignore")
                soup = BeautifulSoup(html, HTML_PARSER)
                # Look for paragraph elements or preview div
                paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 20]
                text_context += "\n".join(paragraphs[:3])  # Keep first few paragraphs
        except Exception as e:
            logger.warning(f"Failed to fetch public preview for {title}: {e}")

        # 2. Supplementary Search for full reprint summaries
        try:
            from data import search_client
            # Clean title to get core search keyword (strip boilerplate)
            clean_title = re.sub(r"《[^》]+》|【[^】]+】", "", title).strip()
            # Search for reprints or posts quoting this article
            search_query = f'"{clean_title[:30]}"'
            logger.info(f"Performing search supplement for DIGITIMES article: {search_query}")
            
            search_articles = search_client.search_industry_info(
                company_name=clean_title[:15],
                symbol="",
                keyword=search_query,
                max_results=3
            )
            
            if search_articles:
                text_context += "\n\n=== 相關社群/轉載情報補強 (Supplementary Search Context) ===\n"
                for art in search_articles:
                    text_context += f"標題: {art['title']}\n"
                    text_context += "\n".join(art["chunks"][:2]) + "\n\n"
        except Exception as e:
            logger.warning(f"Failed to perform search supplement for {title}: {e}")
            
        return text_context.strip()

class SubscriberStrategy(DigitimesScrapingStrategy):
    """
    Scraping strategy for authenticated subscribers.
    Performs POST login to /tech/lgn/check.asp and retrieves full premium text.
    """
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.is_logged_in = False

    def _login(self, session: requests.Session) -> bool:
        login_url = "https://www.digitimes.com.tw/tech/lgn/check.asp"
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": "https://www.digitimes.com.tw/tech/lgn/lgn.asp"
        }
        payload = {
            "checkid": self.username,
            "checkpwd": self.password,
            "fromurl": "login",
            "login_type": "ewr",
            "RememberMyPwd": "True"
        }
        try:
            logger.info(f"Attempting DIGITIMES login as {self.username}...")
            r = session.post(login_url, data=payload, headers=headers, timeout=10)
            # DIGITIMES login usually redirects or writes cookies if successful
            # Check cookies or redirection result
            if r.status_code in (200, 302):
                logger.info("DIGITIMES login request successfully sent.")
                self.is_logged_in = True
                return True
        except Exception as e:
            logger.error(f"DIGITIMES login failed: {e}")
        return False

    def fetch_article_text(self, session: requests.Session, url: str, title: str) -> str:
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        if not self.is_logged_in:
            success = self._login(session)
            if not success:
                logger.warning("Falling back to FreeVisitorStrategy behavior due to failed login.")
                visitor = FreeVisitorStrategy()
                return visitor.fetch_article_text(session, url, title)

        try:
            r = session.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                html = r.content.decode("utf-8", errors="ignore")
                soup = BeautifulSoup(html, HTML_PARSER)
                
                # Retrieve main article text
                # Paid articles are typically inside a div with class/id relating to content, e.g. "news_txt" or class "news_content"
                content_div = soup.find(id="news_txt") or soup.find(class_="news_content") or soup.find(class_="article-body")
                if content_div:
                    paragraphs = [p.get_text(strip=True) for p in content_div.find_all("p") if p.get_text(strip=True)]
                    return "\n".join(paragraphs)
                
                # Fallback to general paragraph scrape
                paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 20]
                return "\n".join(paragraphs)
        except Exception as e:
            logger.error(f"Failed to fetch premium text from {url}: {e}")
            
        visitor = FreeVisitorStrategy()
        return visitor.fetch_article_text(session, url, title)

class DigitimesStrategyFactory:
    """
    Factory class to instantiate the correct scraping strategy based on environment config.
    Part of the Factory Pattern.
    """
    @staticmethod
    def get_strategy() -> DigitimesScrapingStrategy:
        username = os.getenv("DIGITIMES_USERNAME")
        password = os.getenv("DIGITIMES_PASSWORD")
        if username and password:
            return SubscriberStrategy(username, password)
        logger.info("No DIGITIMES credentials found in environment. Using FreeVisitorStrategy.")
        return FreeVisitorStrategy()

class DigitimesCrawler:
    """
    Facade class serving as the main interface to crawl DIGITIMES.
    Part of the Facade Pattern.
    """
    def __init__(self):
        self.session = requests.Session()
        self.strategy = DigitimesStrategyFactory.get_strategy()

    def fetch_latest_news_list(self) -> List[Dict[str, str]]:
        """Crawls the DIGITIMES home page and lists latest tech news headlines."""
        url = "https://www.digitimes.com.tw/"
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        articles = []
        
        try:
            r = self.session.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                logger.error(f"Failed to load DIGITIMES home page, status: {r.status_code}")
                return []
                
            html = r.content.decode("utf-8", errors="ignore")
            soup = BeautifulSoup(html, HTML_PARSER)
            seen_ids = set()
            
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "shwnws.asp" in href:
                    title = a.get_text(strip=True)
                    id_match = re.search(r"id=([a-zA-Z0-9_-]+)", href)
                    if id_match and len(title) > 6:
                        art_id = id_match.group(1)
                        if art_id not in seen_ids:
                            seen_ids.add(art_id)
                            # Convert to absolute URL
                            full_url = href
                            if not href.startswith("http"):
                                full_url = "https://www.digitimes.com.tw" + href
                                
                            articles.append({
                                "id": art_id,
                                "title": title,
                                "url": full_url
                            })
            return articles
        except Exception as e:
            logger.error(f"Failed to crawl DIGITIMES news list: {e}")
            return []

    def fetch_article_content(self, url: str, title: str) -> str:
        """Fetches the content of a single article based on the active strategy."""
        return self.strategy.fetch_article_text(self.session, url, title)

    def close(self):
        """Closes the underlying requests Session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
