"""News collector implementation."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse
from urllib.parse import urljoin
from typing import Any

from bs4 import BeautifulSoup

from collectors.base_collector import BaseCollector
from collectors.base_collector import CollectorResult
from collectors.models import NewsItem
from config import settings
from shared.exceptions import DataCollectionError
from shared.normalization import normalize_text


class NewsCollector(BaseCollector[NewsItem]):
	"""Collect finance headlines from multiple public sources."""

	collector_name = "news"
	source_name = "Multi Source News"
	_article_path_patterns = (
		"/midasin-kulaklari/",
		"/midas-kulaklari/",
		"/midas-akademi/",
		"/borsa-terimleri/",
	)
	_noise_title_pattern = re.compile(r"^(app store|google play|destek|giris|kayit)", re.IGNORECASE)

	def collect(self) -> CollectorResult[NewsItem]:
		items: list[NewsItem] = []
		failed_sources = 0

		for source_url in settings.news_source_list:
			try:
				response = self._request(source_url)
			except DataCollectionError:
				failed_sources += 1
				continue

			content_type = str(response.headers.get("Content-Type") or "").lower()
			text = response.text

			if "xml" in content_type or "rss" in content_type or source_url.lower().endswith((".xml", "/rss")):
				items.extend(self._parse_rss_items(text, source_url))
			else:
				soup = BeautifulSoup(text, "html.parser")
				items.extend(self._parse_items(soup, base_url=source_url, source_label=self._source_from_url(source_url)))

		unique: list[NewsItem] = []
		seen: set[tuple[str, str]] = set()
		for item in items:
			key = (item.title.strip().lower(), item.url.strip().lower())
			if key in seen:
				continue
			seen.add(key)
			unique.append(item)

		if not unique:
			self._record_failure("No news items could be extracted from configured sources.")
			raise DataCollectionError(
				f"{self.collector_name} collector could not extract any news items"
			)

		self._record_success()
		return self._build_result(
			items=unique,
			metadata={"sources": settings.news_source_list, "failed_sources": failed_sources, "count": len(unique)},
		)

	def _parse_items(
		self,
		soup: BeautifulSoup,
		*,
		base_url: str | None = None,
		source_label: str | None = None,
	) -> list[NewsItem]:
		items: list[NewsItem] = []
		seen_urls: set[str] = set()
		base = base_url or settings.news_source_url
		source = source_label or self.source_name

		for link in soup.find_all("a", href=True):
			title = self._extract_title(link)
			href = urljoin(base, link["href"])
			if not self._is_relevant_link(href, title):
				continue

			if len(title) < 20 or href in seen_urls:
				continue

			seen_urls.add(href)
			metadata = self._build_news_metadata(title)
			metadata["source"] = source
			items.append(
				NewsItem(
					title=title,
					url=href,
					source=source,
					summary=json.dumps(metadata, ensure_ascii=False),
				)
			)

			if len(items) >= 50:
				break

		return items

	def _parse_rss_items(self, xml_text: str, source_url: str) -> list[NewsItem]:
		soup = BeautifulSoup(xml_text, "xml")
		items: list[NewsItem] = []
		for node in soup.find_all(["item", "entry"]):
			title_tag = node.find("title")
			link_tag = node.find("link")
			date_tag = node.find("pubDate") or node.find("published") or node.find("updated")

			title = normalize_text(title_tag.get_text(" ", strip=True) if title_tag else "")
			if link_tag is None:
				continue

			href = str(link_tag.get("href") or link_tag.get_text(" ", strip=True) or "").strip()
			href = urljoin(source_url, href)
			if not self._is_relevant_link(href, title):
				continue

			published = normalize_text(date_tag.get_text(" ", strip=True) if date_tag else "")
			metadata = self._build_news_metadata(title)
			metadata["source"] = self._source_from_url(source_url)
			if published:
				metadata["publish_date"] = published

			items.append(
				NewsItem(
					title=title,
					url=href,
					source=self._source_from_url(source_url),
					summary=json.dumps(metadata, ensure_ascii=False),
				)
			)

			if len(items) >= 80:
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

		if "/rss" in lower_href or lower_href.endswith(".xml"):
			return False

		return lower_href.count("-") >= 2 and "/" in lower_href

	def _source_from_url(self, value: str) -> str:
		host = urlparse(value).netloc.lower().replace("www.", "")
		if not host:
			return self.source_name
		return host

	def _build_news_metadata(self, title: str) -> dict[str, Any]:
		tickers = sorted(set(re.findall(r"\b[A-ZÇĞİÖŞÜ]{4,5}\b", title.upper())))
		company_names = self._guess_company_names(title)
		return {
			"source": self.source_name,
			"publish_date": "",
			"company_names": company_names,
			"ticker_candidates": tickers,
			"detected_tickers": tickers,
		}

	def _guess_company_names(self, title: str) -> list[str]:
		candidates = re.findall(r"[A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+){0,2}", title)
		return [normalize_text(item) for item in candidates[:5] if len(normalize_text(item)) >= 4]

