from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class TopKMetrics:
    top_k: int
    samples: int
    win_rate_pct: float
    average_return_pct: float
    precision_pct: float
    false_positives: int


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _iter_history_entries(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for day in history:
        recommendations = day.get("recommendations")
        if not isinstance(recommendations, list):
            continue
        for item in recommendations:
            if isinstance(item, dict):
                entries.append(item)
    return entries


def _topk_metrics(history: list[dict[str, Any]], top_k: int) -> TopKMetrics:
    closed: list[dict[str, Any]] = []
    for day in history:
        recommendations = day.get("recommendations")
        if not isinstance(recommendations, list):
            continue
        subset = recommendations[:top_k]
        for item in subset:
            if _safe_upper(item.get("status")) != "CLOSED":
                continue
            result = _safe_upper(item.get("result"))
            if result not in {"WIN", "LOSE"}:
                continue
            closed.append(item)

    if not closed:
        return TopKMetrics(top_k=top_k, samples=0, win_rate_pct=0.0, average_return_pct=0.0, precision_pct=0.0, false_positives=0)

    wins = [item for item in closed if _safe_upper(item.get("result")) == "WIN"]
    losses = [item for item in closed if _safe_upper(item.get("result")) == "LOSE"]
    avg_return = mean(_to_float(item.get("profit_pct"), 0.0) for item in closed)
    win_rate = (len(wins) / len(closed)) * 100.0

    return TopKMetrics(
        top_k=top_k,
        samples=len(closed),
        win_rate_pct=win_rate,
        average_return_pct=avg_return,
        precision_pct=win_rate,
        false_positives=len(losses),
    )


def _expected_gain_validation(entries: list[dict[str, Any]]) -> dict[str, Any]:
    validated: list[dict[str, Any]] = []
    for item in entries:
        if _safe_upper(item.get("status")) != "CLOSED":
            continue

        expected_gain = _to_float(item.get("expected_gain_pct"), 0.0)
        if expected_gain <= 0:
            entry_price = _to_float(item.get("entry_price"), 0.0)
            target_price = _to_float(item.get("current_target"), _to_float(item.get("take_profit_1"), 0.0))
            if entry_price > 0 and target_price > 0:
                expected_gain = ((target_price - entry_price) / entry_price) * 100.0
        if expected_gain <= 0:
            continue

        # max_gain is strongest indicator of whether predicted upside was seen at any point.
        realized_peak = _to_float(item.get("max_gain"), _to_float(item.get("profit_pct"), 0.0))
        realized_close = _to_float(item.get("profit_pct"), 0.0)
        hit_peak = realized_peak >= expected_gain
        hit_close = realized_close >= expected_gain

        validated.append(
            {
                "ticker": str(item.get("ticker") or "").upper(),
                "expected_gain_pct": round(expected_gain, 4),
                "realized_peak_pct": round(realized_peak, 4),
                "realized_close_pct": round(realized_close, 4),
                "hit_peak": hit_peak,
                "hit_close": hit_close,
            }
        )

    if not validated:
        return {
            "samples": 0,
            "peak_hit_rate_pct": 0.0,
            "close_hit_rate_pct": 0.0,
            "average_expected_gain_pct": 0.0,
            "average_realized_peak_pct": 0.0,
            "average_realized_close_pct": 0.0,
            "details": [],
        }

    peak_hits = sum(1 for row in validated if row["hit_peak"])
    close_hits = sum(1 for row in validated if row["hit_close"])

    return {
        "samples": len(validated),
        "peak_hit_rate_pct": round((peak_hits / len(validated)) * 100.0, 2),
        "close_hit_rate_pct": round((close_hits / len(validated)) * 100.0, 2),
        "average_expected_gain_pct": round(mean(row["expected_gain_pct"] for row in validated), 4),
        "average_realized_peak_pct": round(mean(row["realized_peak_pct"] for row in validated), 4),
        "average_realized_close_pct": round(mean(row["realized_close_pct"] for row in validated), 4),
        "details": validated,
    }


def _load_blocked_tickers(config_dir: Path) -> set[str]:
    payload = _read_json(config_dir / "halal_filter.json", {"blocked_tickers": []})
    blocked = payload.get("blocked_tickers") if isinstance(payload, dict) else []
    return {str(value).strip().upper() for value in blocked if str(value).strip()}


def _halal_audit(entries: list[dict[str, Any]], blocked_tickers: set[str]) -> dict[str, Any]:
    offending = []
    for item in entries:
        ticker = _safe_upper(item.get("ticker"))
        if not ticker:
            continue
        if ticker in blocked_tickers:
            offending.append(ticker)

    unique_offending = sorted(set(offending))
    return {
        "blocked_ticker_count": len(blocked_tickers),
        "recommended_blocked_tickers": unique_offending,
        "violations": len(unique_offending),
        "passed": len(unique_offending) == 0,
    }


def _old_sort_key(item: dict[str, Any]) -> tuple[float, float, float, float, float, str]:
    expected_gain = _to_float(item.get("expected_gain_pct"), 0.0)
    confidence = _to_float(item.get("confidence"), _to_float(item.get("overall_score"), 0.0))
    technical_score = _to_float(item.get("technical_score"), 0.0)
    total_score = _to_float(item.get("total_score"), _to_float(item.get("overall_score"), 0.0))
    target_expected_gain = 10.0
    return (
        abs(target_expected_gain - expected_gain),
        -expected_gain,
        -confidence,
        -technical_score,
        -total_score,
        str(item.get("ticker") or ""),
    )


def _dynamic_min_expected_gain(item: dict[str, Any]) -> float:
    current_price = _to_float(item.get("current_price"), _to_float(item.get("entry_price"), 0.0))
    atr_value = _to_float(item.get("atr"), 0.0)
    trend_strength = _to_float(item.get("trend_strength"), 0.0)
    atr_ratio = (atr_value / max(current_price, 1e-9)) if current_price > 0 else 0.0
    volatility_floor = max(1.6, min(3.0, atr_ratio * 180.0))

    trend_discount = 0.0
    if trend_strength >= 75:
        trend_discount = 0.3
    elif trend_strength >= 65:
        trend_discount = 0.15

    return max(1.5, min(3.0, volatility_floor - trend_discount))


def _new_sort_key(item: dict[str, Any]) -> tuple[float, float, float, float, float, str]:
    expected_gain = _to_float(item.get("expected_gain_pct"), 0.0)
    confidence = _to_float(item.get("confidence"), _to_float(item.get("overall_score"), _to_float(item.get("total_score"), 0.0)))
    trend_strength = _to_float(item.get("trend_strength"), 0.0)
    risk_reward = _to_float(item.get("risk_reward_ratio"), 0.0)
    total_score = _to_float(item.get("total_score"), _to_float(item.get("overall_score"), 0.0))

    quality_rank = (
        (total_score * 0.52)
        + (confidence * 0.22)
        + (min(100.0, expected_gain * 8.0) * 0.16)
        + (min(100.0, risk_reward * 25.0) * 0.10)
    )
    return (
        -quality_rank,
        -expected_gain,
        -confidence,
        -trend_strength,
        -total_score,
        str(item.get("ticker") or ""),
    )


def _confidence_gate_reasons(item: dict[str, Any], min_rr: float = 1.2) -> list[str]:
    reasons: list[str] = []
    decision = _safe_upper(item.get("decision"))
    confidence = _to_float(item.get("confidence"), _to_float(item.get("total_score"), _to_float(item.get("overall_score"), 0.0)))
    risk_reward = _to_float(item.get("risk_reward_ratio"), 0.0)
    trend = str(item.get("trend") or "Neutral").strip().lower()
    news_sentiment = str(item.get("news_sentiment") or "Neutral").strip().lower()
    macd_state = str(item.get("macd_state") or "Neutral").strip().lower()

    if decision in {"WAIT", "SELL", "NO TRADE", "ENTRY MISSED", "EXIT"}:
        reasons.append("decision")
    if confidence < 62.0:
        reasons.append("confidence")
    if risk_reward < max(1.2, min_rr):
        reasons.append("risk_reward")
    if trend == "bearish" and decision in {"BUY", "BUY NOW", "LIMIT BUY"}:
        reasons.append("trend_conflict")
    if news_sentiment == "negative" and decision in {"BUY", "BUY NOW", "LIMIT BUY"}:
        reasons.append("news_conflict")
    if macd_state == "bearish" and trend == "bullish" and decision in {"BUY", "BUY NOW", "LIMIT BUY"}:
        reasons.append("trend_macd_conflict")

    return reasons


def _bist30_default_set() -> set[str]:
    # Reference set used in current project diagnostics.
    return {
        "AKBNK", "ALARK", "ASELS", "ASTOR", "BIMAS", "DOAS", "EKGYO", "ENKAI", "EREGL", "FROTO",
        "GARAN", "GUBRF", "HEKTS", "ISCTR", "KCHOL", "KOZAA", "KOZAL", "MGROS", "ODAS", "PETKM",
        "PGSUS", "SAHOL", "SASA", "SISE", "TAVHL", "TCELL", "THYAO", "TOASO", "TUPRS", "YKBNK",
    }


def _load_benchmark_sets(config_dir: Path, data_dir: Path) -> tuple[set[str], set[str], bool]:
    market_rows = _read_json(data_dir / "market.json", [])
    if not isinstance(market_rows, list):
        market_rows = []

    by_cap: list[tuple[str, float]] = []
    for row in market_rows:
        if not isinstance(row, dict):
            continue
        ticker = _safe_upper(row.get("symbol") or row.get("ticker"))
        if not ticker:
            continue
        market_cap = _to_float(row.get("market_cap"), 0.0)
        if market_cap <= 0:
            continue
        by_cap.append((ticker, market_cap))

    by_cap.sort(key=lambda item: item[1], reverse=True)
    proxy_b100 = {ticker for ticker, _ in by_cap[:100]}

    benchmark_file = config_dir / "index_benchmarks.json"
    payload = _read_json(benchmark_file, {})
    if isinstance(payload, dict):
        b30 = {
            str(value).strip().upper()
            for value in payload.get("bist30", [])
            if str(value).strip()
        }
        b100 = {
            str(value).strip().upper()
            for value in payload.get("bist100", [])
            if str(value).strip()
        }
        if b30 and b100:
            return b30, b100, False
        if b30 and not b100:
            return b30, proxy_b100, True
    return _bist30_default_set(), proxy_b100, True


def _ab_snapshot_compare(
    scoring_rows: list[dict[str, Any]],
    *,
    top_n: int = 20,
    bist30_set: set[str],
    bist100_set: set[str],
    bist100_is_proxy: bool,
) -> dict[str, Any]:
    eligible_old = [
        row for row in scoring_rows
        if not bool(row.get("hard_filtered")) and _to_float(row.get("expected_gain_pct"), 0.0) >= 3.0
    ]

    eligible_new = [
        row for row in scoring_rows
        if not bool(row.get("hard_filtered")) and _to_float(row.get("expected_gain_pct"), 0.0) >= _dynamic_min_expected_gain(row)
    ]

    old_top = sorted(eligible_old, key=_old_sort_key)[:top_n]
    new_top_pre_gate = sorted(eligible_new, key=_new_sort_key)[:top_n]
    gate_fail_reasons: dict[str, int] = defaultdict(int)
    new_top_after_gate: list[dict[str, Any]] = []
    for row in new_top_pre_gate:
        reasons = _confidence_gate_reasons(row)
        if not reasons:
            new_top_after_gate.append(row)
            continue
        for reason in reasons:
            gate_fail_reasons[reason] += 1

    def _tickers(rows: list[dict[str, Any]]) -> list[str]:
        return [str(row.get("ticker") or "").upper() for row in rows if str(row.get("ticker") or "").strip()]

    old_tickers = _tickers(old_top)
    new_tickers = _tickers(new_top_pre_gate)
    new_tickers_after_gate = _tickers(new_top_after_gate)

    return {
        "snapshot_scored_total": len(scoring_rows),
        "old_eligible_total": len(eligible_old),
        "new_eligible_total": len(eligible_new),
        "old_top_tickers": old_tickers,
        "new_top_tickers": new_tickers,
        "new_top_tickers_after_gate": new_tickers_after_gate,
        "old_top_bist30": [ticker for ticker in old_tickers if ticker in bist30_set],
        "new_top_bist30": [ticker for ticker in new_tickers if ticker in bist30_set],
        "new_top_bist30_after_gate": [ticker for ticker in new_tickers_after_gate if ticker in bist30_set],
        "old_top_bist100": [ticker for ticker in old_tickers if ticker in bist100_set],
        "new_top_bist100": [ticker for ticker in new_tickers if ticker in bist100_set],
        "new_top_bist100_after_gate": [ticker for ticker in new_tickers_after_gate if ticker in bist100_set],
        "bist100_source": "proxy_market_cap_top100" if bist100_is_proxy else "config_exact_list",
        "new_gate_pass_count": len(new_top_after_gate),
        "new_gate_fail_reason_counts": dict(sorted(gate_fail_reasons.items(), key=lambda item: (-item[1], item[0]))),
    }


def build_report(data_dir: Path, config_dir: Path, top_n: int) -> dict[str, Any]:
    history = _read_json(data_dir / "history.json", [])
    if not isinstance(history, list):
        history = []

    entries = _iter_history_entries(history)

    topk = {
        str(k): _topk_metrics(history, k).__dict__
        for k in (1, 3, 5, 10)
    }

    expected_gain = _expected_gain_validation(entries)
    blocked_tickers = _load_blocked_tickers(config_dir)
    halal = _halal_audit(entries, blocked_tickers)

    scoring_rows = _read_json(data_dir / "bist_scoring_log.json", [])
    if not isinstance(scoring_rows, list):
        scoring_rows = []
    benchmark_b30, benchmark_b100, bist100_is_proxy = _load_benchmark_sets(config_dir=config_dir, data_dir=data_dir)
    ab_compare = _ab_snapshot_compare(
        scoring_rows,
        top_n=top_n,
        bist30_set=benchmark_b30,
        bist100_set=benchmark_b100,
        bist100_is_proxy=bist100_is_proxy,
    )

    by_ticker: dict[str, dict[str, float]] = defaultdict(lambda: {
        "count": 0,
        "avg_expected": 0.0,
        "avg_realized_peak": 0.0,
        "avg_realized_close": 0.0,
        "peak_hits": 0,
    })

    for row in expected_gain.get("details", []):
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        bucket = by_ticker[ticker]
        bucket["count"] += 1
        bucket["avg_expected"] += _to_float(row.get("expected_gain_pct"), 0.0)
        bucket["avg_realized_peak"] += _to_float(row.get("realized_peak_pct"), 0.0)
        bucket["avg_realized_close"] += _to_float(row.get("realized_close_pct"), 0.0)
        bucket["peak_hits"] += 1 if bool(row.get("hit_peak")) else 0

    ticker_summary: list[dict[str, Any]] = []
    for ticker, bucket in by_ticker.items():
        count = int(bucket["count"])
        if count <= 0:
            continue
        ticker_summary.append(
            {
                "ticker": ticker,
                "samples": count,
                "avg_expected_gain_pct": round(bucket["avg_expected"] / count, 4),
                "avg_realized_peak_pct": round(bucket["avg_realized_peak"] / count, 4),
                "avg_realized_close_pct": round(bucket["avg_realized_close"] / count, 4),
                "peak_hit_rate_pct": round((bucket["peak_hits"] / count) * 100.0, 2),
            }
        )

    ticker_summary.sort(key=lambda item: (item["peak_hit_rate_pct"], item["samples"], item["avg_realized_peak_pct"]), reverse=True)

    return {
        "inputs": {
            "history_path": str((data_dir / "history.json").as_posix()),
            "scoring_log_path": str((data_dir / "bist_scoring_log.json").as_posix()),
            "halal_filter_path": str((config_dir / "halal_filter.json").as_posix()),
            "benchmark_path": str((config_dir / "index_benchmarks.json").as_posix()),
        },
        "history_entries": len(entries),
        "topk_metrics": topk,
        "expected_gain_validation": {
            key: value
            for key, value in expected_gain.items()
            if key != "details"
        },
        "halal_audit": halal,
        "ab_snapshot_compare": ab_compare,
        "ticker_expected_gain_summary_top20": ticker_summary[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot-based backtest and recommendation quality report")
    parser.add_argument("--data-dir", default="storage/data", help="Data directory path")
    parser.add_argument("--config-dir", default="storage/config", help="Config directory path")
    parser.add_argument("--output", default="storage/data/snapshot_backtest_report.json", help="Output JSON path")
    parser.add_argument("--top-n", type=int, default=20, help="Top-N size for A/B snapshot compare")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    config_dir = Path(args.config_dir)
    output_path = Path(args.output)

    report = build_report(data_dir=data_dir, config_dir=config_dir, top_n=max(5, int(args.top_n)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Report created: {output_path.as_posix()}")
    print(f"History entries: {report['history_entries']}")
    print(f"Halal violations: {report['halal_audit']['violations']}")
    print(f"Expected gain samples: {report['expected_gain_validation']['samples']}")


if __name__ == "__main__":
    main()
