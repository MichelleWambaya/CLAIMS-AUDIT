"""
§5.3 Pricing anomalies.

IQR-based outlier detection per benefit category: flag claims priced above
Q3 + multiplier * IQR for their category. Multiplier configurable per
category (falls back to the default multiplier) since some categories
legitimately have wider price variance (e.g. inpatient/surgical vs.
routine outpatient consults).
"""
import math
from dataclasses import dataclass
from typing import Any, Dict, List

from .config import RuleConfig, DEFAULT_CONFIG


@dataclass
class PricingAnomalyFlag:
    row_index: int
    category: str
    amount: float
    q1: float
    q3: float
    iqr: float
    threshold: float
    multiplier_used: float


def _quartiles(values: List[float]) -> "tuple[float, float]":
    """Q1/Q3 via linear interpolation (same convention as numpy default)."""
    s = sorted(values)
    n = len(s)

    def percentile(p: float) -> float:
        if n == 1:
            return s[0]
        idx = p * (n - 1)
        lo = math.floor(idx)
        hi = math.ceil(idx)
        if lo == hi:
            return s[int(idx)]
        frac = idx - lo
        return s[lo] + (s[hi] - s[lo]) * frac

    return percentile(0.25), percentile(0.75)


def detect_pricing_anomalies(
    rows: List[Dict[str, Any]],
    config: RuleConfig = DEFAULT_CONFIG,
) -> List[PricingAnomalyFlag]:
    """
    rows: list of dicts with 'row_index', 'category', 'amount' (float).
    Rows missing amount or category are skipped (handled by §5.5-style
    completeness checks elsewhere, not silently double-flagged here).
    """
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        cat = r.get("category")
        amt = r.get("amount")
        if cat is None or amt is None:
            continue
        by_category.setdefault(cat, []).append(r)

    flags: List[PricingAnomalyFlag] = []

    for category, cat_rows in by_category.items():
        if len(cat_rows) < 4:
            # not enough data points for a meaningful IQR in this category
            continue
        amounts = [float(r["amount"]) for r in cat_rows]
        q1, q3 = _quartiles(amounts)
        iqr = q3 - q1
        multiplier = config.iqr_multiplier_by_category.get(
            category, config.iqr_multiplier_default
        )
        threshold = q3 + multiplier * iqr

        for r in cat_rows:
            amount = float(r["amount"])
            if amount > threshold:
                flags.append(PricingAnomalyFlag(
                    row_index=r["row_index"],
                    category=category,
                    amount=amount,
                    q1=q1,
                    q3=q3,
                    iqr=iqr,
                    threshold=threshold,
                    multiplier_used=multiplier,
                ))

    return flags
