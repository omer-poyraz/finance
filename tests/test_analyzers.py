from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pandas as pd

from analyzers import FinancialAnalyzer
from analyzers import NewsAnalyzer
from analyzers import RiskAnalyzer
from analyzers import TechnicalAnalyzer
from collectors.models import NewsItem


def _market_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [10, 10.5, 11, 11.2, 11.5, 11.8, 12.1, 12.4],
            "high": [10.6, 11, 11.2, 11.7, 12.0, 12.2, 12.6, 12.9],
            "low": [9.8, 10.2, 10.7, 11.0, 11.3, 11.5, 11.9, 12.1],
            "close": [10.4, 10.8, 11.1, 11.5, 11.8, 12.0, 12.4, 12.7],
            "volume": [1000, 1200, 1400, 1500, 1700, 1900, 2200, 2600],
        }
    )


def test_news_analyzer_scores_positive_headlines_higher() -> None:
    analyzer = NewsAnalyzer(
        {
            "positive": {
                "yeni sozlesme": 30,
                "rekor kar": 28,
                "yatirim": 25,
                "temettu": 24,
                "kapasite artisi": 28,
                "siparis": 18,
            },
            "negative": {},
        }
    )
    score = analyzer.score(
        [
            NewsItem(
                title="Sirket yeni sozlesme ile rekor kar ve yatirim acikladi",
                url="https://example.com/1",
                source="test",
                published_at=datetime.now(UTC),
            ),
            NewsItem(
                title="Temettu ve kapasite artisi aciklandi, yeni siparis geldi",
                url="https://example.com/2",
                source="test",
                published_at=datetime.now(UTC),
            ),
        ]
    )

    assert score > 60


def test_technical_analyzer_scores_trending_frame() -> None:
    analyzer = TechnicalAnalyzer()
    score = analyzer.score(_market_frame())

    assert 0 <= score <= 100
    assert score > 40


def test_risk_analyzer_scores_within_bounds() -> None:
    analyzer = RiskAnalyzer()
    score = analyzer.score(_market_frame())

    assert 0 <= score <= 100


def test_financial_analyzer_scores_reasonable_metrics() -> None:
    analyzer = FinancialAnalyzer()
    score = analyzer.score(
        {
            "revenue_growth": 18.0,
            "net_margin": 16.0,
            "debt_to_equity": 0.4,
            "current_ratio": 1.8,
            "roe": 22.0,
        }
    )

    assert 0 <= score <= 100
    assert score > 60
