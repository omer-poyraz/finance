"""News collector implementation."""

from __future__ import annotations

import re
from urllib.parse import urljoin
from typing import Any

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
	_article_path_patterns = (
		"/midasin-kulaklari/",
		"/midas-kulaklari/",
		"/midas-akademi/",
		"/borsa-terimleri/",
	)
	_noise_title_pattern = re.compile(r"^(app store|google play|destek|giris|kayit)", re.IGNORECASE)

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
			title = self._extract_title(link)
			href = urljoin(settings.news_source_url, link["href"])
			if not self._is_relevant_link(href, title):
				continue

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

	def _extract_title(self, link: Any) -> str:
		for attr in ("title", "aria-label", "data-title"):
			value = str(link.get(attr) or "").strip()
			if len(value) >= 20:
				return value

		text = link.get_text(" ", strip=True)
		if text:
			return text

		return ""

	def _is_relevant_link(self, href: str, title: str) -> bool:
		lower_href = href.lower()
		lower_title = title.lower().strip()
		if not lower_href.startswith("http"):
			return False
		if self._noise_title_pattern.match(lower_title):
			return False
		if "javascript:" in lower_href or "mailto:" in lower_href:
			return False

		if any(pattern in lower_href for pattern in self._article_path_patterns):
			return True

		return lower_href.count("-") >= 3 and "/" in lower_href

