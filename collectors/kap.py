
"""KAP announcement collector."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collectors.base_collector import BaseCollector
from collectors.base_collector import CollectorResult
from collectors.models import AnnouncementItem
from config import settings
from shared.exceptions import DataCollectionError


class KapCollector(BaseCollector[AnnouncementItem]):
	"""Collect KAP announcements from the public announcements page."""

	collector_name = "kap"
	source_name = "KAP"

	def collect(self) -> CollectorResult[AnnouncementItem]:
		response = self._request(settings.kap_source_url)
		soup = BeautifulSoup(response.text, "html.parser")
		items = self._parse_items(soup)

		if not items:
			self._record_failure("No KAP announcements could be extracted.")
			raise DataCollectionError(
				f"{self.collector_name} collector could not extract any announcements"
			)

		self._record_success()
		return self._build_result(
			items=items,
			metadata={"source_url": settings.kap_source_url, "count": len(items)},
		)

	def _parse_items(self, soup: BeautifulSoup) -> list[AnnouncementItem]:
		items: list[AnnouncementItem] = []
		seen_urls: set[str] = set()

		for link in soup.find_all("a", href=True):
			title = link.get_text(" ", strip=True)
			href = urljoin(settings.kap_source_url, link["href"])
			if len(title) < 15 or href in seen_urls:
				continue

			seen_urls.add(href)
			items.append(
				AnnouncementItem(
					title=title,
					url=href,
					source=self.source_name,
				)
			)

			if len(items) >= 50:
				break

		return items

