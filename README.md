# AI Personal Halal Investment Assistant V3

Bu proje lokal calisan, Telegram bildirimli, faizsiz filtreli (halal) gunluk yatirim asistanidir.

## V3 Ozeti

- Sadece AL/SAT degil, portfoy yonetimi de yapar.
- Halal filtre AI analizinden once calisir.
- BIST ve US piyasasi birlikte desteklenir.
- Her hisse icin 0-100 guven skoru, trend gucu ve trend suresi uretir.
- Karar seti: `BUY`, `HOLD`, `PARTIAL TAKE PROFIT`, `RAISE STOP`, `EXIT`, `WAIT IN CASH`.
- Market bazli bagimsiz scheduler calisir.
- Gemini API Key Pool failover desteklenir.

## Kurulum

1. Sanal ortam olustur.

```powershell
python -m venv .venv
```

2. Bagimliliklari yukle.

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

3. Ortam dosyasini hazirla.

```powershell
Copy-Item .env.example .env
```

## Ortam Degiskenleri

Zorunlu:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Opsiyonel ama tavsiye edilir:

- `GEMINI_API_KEY`
- `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, ...
- `GEMINI_MODEL` (varsayilan `gemini-2.5-flash`)
- `MARKETS` (varsayilan `BIST,US`)
- `US_MARKET_TICKERS` (varsayilan `GOOGL,AMZN,TSLA,META,NFLX`)
- `TOTAL_CAPITAL` (varsayilan `10000`)
- `TIMEZONE` (varsayilan `Europe/Istanbul`)
- `SCHEDULER_BIST_ENABLED`, `SCHEDULER_BIST_HOUR`, `SCHEDULER_BIST_MINUTE`
- `SCHEDULER_US_ENABLED`, `SCHEDULER_US_HOUR`, `SCHEDULER_US_MINUTE`
- `SCHEDULER_PORTFOLIO_ENABLED`, `SCHEDULER_PORTFOLIO_HOUR`, `SCHEDULER_PORTFOLIO_MINUTE`

## Mimari (Engine Bazli)

- `HalalFilterEngine`: Helal olmayan hisseleri eler.
- `TechnicalEngine`: EMA, SMA, RSI, MACD, Bollinger, ATR, ADX, SuperTrend, Fibonacci, Destek/Direnc, Hacim.
- `NewsEngine` (mevcut analiz akisi): Haber sentiment ve ticker bazli ozet.
- `FundamentalEngine`: Temel kalite skoru uretir.
- `MarketIntelligenceEngine`: Momentum, volatilite, likidite ile piyasa zekasi skoru.
- `TrendEngine`: 0-100 trend gucu ve tahmini trend suresi.
- `DecisionEngine`: Nihai karari uretir (`BUY/HOLD/PARTIAL TAKE PROFIT/RAISE STOP/EXIT/WAIT IN CASH`).
- `PortfolioEngine`: Acik pozisyonlari gunluk yeniden degerlendirir.
- `CapitalAllocationEngine`: Guven skoru bazli tutar dagitimi yapar.

## Calisma Akisi

1. Veri toplanir (`news`, `kap`, `market`, `us_market`).
2. `HalalFilterEngine` market verisini filtreler.
3. Haber ve ticker analizi yapilir.
4. Teknik + temel + market intelligence + trend analizi birlestirilir.
5. Nihai karar ve guven puani uretilir.
6. Sermaye dagilimi hesaplanir.
7. Portfoy yeniden analiz edilir.
8. Gemini son asamada niteliksel yorum ekler.
9. Telegram ozeti gonderilir.

## Scheduler (Turkiye Saati)

- `09:45`: BIST Daily Report
- `16:00`: US Market Report
- `22:30` (opsiyonel): Portfolio Update

Tum schedulerlar config ile acilip kapanabilir.

## Portfoy Dosyasi

`storage/data/portfolio.json` formati:

```json
[
  {
    "ticker": "THYAO",
    "average_price": 190.0,
    "quantity": 10,
    "current_profit": 0.0,
    "current_stop": 180.0,
    "current_decision": "HOLD"
  }
]
```

## Onemli JSON Dosyalari

- `storage/config/halal_filter.json`
- `storage/data/market.json`
- `storage/data/market_analysis.json`
- `storage/data/recommendations.json`
- `storage/data/portfolio.json`
- `storage/data/portfolio_analysis.json`

## API Uclari

- `/collect/news`
- `/collect/kap`
- `/collect/market`
- `/analyze/news`
- `/analyze/market`
- `/analyze/tickers`
- `/recommendations`
- `/portfolio`
- `/portfolio/analyze`
- `/history`
- `/performance`
- `/run/bist`
- `/run/us`
- `/run/portfolio`

## Baslatma

```powershell
.\run.bat
```

veya VS Code task: `Start Project`
