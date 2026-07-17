from __future__ import annotations

from bs4 import BeautifulSoup

from collectors import BaseCollector
from collectors import CollectorManager
from collectors import NewsCollector
from collectors.base_collector import CollectorResult
from collectors.models import NewsItem


class DummyCollector(BaseCollector[str]):
    collector_name = "dummy"
    source_name = "dummy-source"

    def collect(self) -> CollectorResult[str]:
        self._record_success()
        return self._build_result(items=["ok"], metadata={"count": 1})


def test_collector_manager_collects_registered_collectors() -> None:
    manager = CollectorManager()
    manager.register(DummyCollector())

    results = manager.collect_all()

    assert results["dummy"].success is True
    assert results["dummy"].items == ["ok"]


def test_news_collector_parses_anchor_tags() -> None:
    collector = NewsCollector()
    soup = BeautifulSoup(
        """
        <html>
          <body>
            <a href="/news/1">Company reports strong quarterly profit growth</a>
            <a href="https://example.com/news/2">Another positive contract announcement</a>
          </body>
        </html>
        """,
        "html.parser",
    )

    items = collector._parse_items(soup)

    assert items
    assert all(isinstance(item, NewsItem) for item in items)
