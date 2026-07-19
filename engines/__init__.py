"""Modular analysis engines for investment assistant V2."""

from engines.capital_allocation_engine import CapitalAllocationEngine
from engines.fundamental_engine import FundamentalEngine
from engines.halal_filter_engine import HalalFilterEngine
from engines.market_intelligence_engine import MarketIntelligenceEngine
from engines.portfolio_engine import PortfolioEngine
from engines.technical_engine import TechnicalEngine
from engines.trend_engine import TrendEngine

__all__ = [
    "CapitalAllocationEngine",
    "FundamentalEngine",
    "HalalFilterEngine",
    "MarketIntelligenceEngine",
    "PortfolioEngine",
    "TechnicalEngine",
    "TrendEngine",
]
