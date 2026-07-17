import requests
import json
import os
from bs4 import BeautifulSoup
"""Backward compatibility module for older imports."""

from collectors.news import NewsCollector

__all__ = ["NewsCollector"]
from collectors.base_collector import BaseCollector


class NewsCollector(BaseCollector):

    URL = "https://www.getmidas.com/borsa-haberleri/"

    def collect(self):

        response = requests.get(
            self.URL,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        soup = BeautifulSoup(response.text, "html.parser")

        news = []

        articles = soup.find_all("a")

        for article in articles:

            text = article.get_text(strip=True)

            href = article.get("href")

            if len(text) < 20:
                continue

            if href is None:
                continue

            if href.startswith("/"):
                href = "https://www.getmidas.com" + href

            news.append({
                "title": text,
                "url": href
            })

        unique = []

        seen = set()

        for item in news:

            if item["title"] in seen:
                continue

            seen.add(item["title"])

            unique.append(item)

        os.makedirs("data", exist_ok=True)

        with open(
                "data/news.json",
                "w",
                encoding="utf8") as file:

            json.dump(
                unique,
                file,
                ensure_ascii=False,
                indent=4
            )

        print(f"{len(unique)} haber kaydedildi.")
