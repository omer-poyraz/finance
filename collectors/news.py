"""News collector implementation."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collectors.base_collector import BaseCollector
from collectors.base_collector import CollectorResult
from collectors.models import NewsItem
from config import settings
from shared.exceptions import DataCollectionError


class NewsCollector(BaseCollector[NewsItem]):
	"""Collect finance headlines from a public news source."""

	collector_name = "news"
	source_name = "Borsa News"

	def collect(self) -> CollectorResult[NewsItem]:
		response = self._request(settings.news_source_url)
		soup = BeautifulSoup(response.text, "html.parser")
		items = self._parse_items(soup)

		if not items:
			self._record_failure("No news items could be extracted from the page.")
			raise DataCollectionError(
				f"{self.collector_name} collector could not extract any news items"
			)

		self._record_success()
		return self._build_result(
			items=items,
			metadata={"source_url": settings.news_source_url, "count": len(items)},
		)

	def _parse_items(self, soup: BeautifulSoup) -> list[NewsItem]:
		items: list[NewsItem] = []
		seen_urls: set[str] = set()

		for link in soup.find_all("a", href=True):
			title = link.get_text(" ", strip=True)
			href = urljoin(settings.news_source_url, link["href"])
			if len(title) < 20 or href in seen_urls:
				continue

			seen_urls.add(href)
			items.append(
				NewsItem(
					title=title,
					url=href,
					source=self.source_name,
				)
			)

			if len(items) >= 50:
				break

		return items

