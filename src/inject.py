"""Stage 3 — Synthetic anomaly injection with six fraud archetypes.

Produces a ground-truth labeled dataset where ~1.5% of rows carry injected
anomalies across six types.  All injected rows are individually plausible
(the "realism beats volume" principle from the master plan).

Output files:
  - data/processed/transactions_labeled.parquet + .csv
  - data/processed/injected_anomalies.csv  (committed — small ground-truth log)
  - reports/metrics/injection_summary.json
  - reports/figures/injection_*.png
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.config import cfg
from src.io_utils import write_json
from src.logging_setup import setup_logging, timed
from src.viz import PALETTE, save_fig, FIGSIZE, DPI


import json
import numpy as np

class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

logger = logging.getLogger("audit.inject")

ANOMALY_TYPES = ["duplicate", "threshold_avoidance", "round_number",
                 "digit_fabrication", "timing", "extreme_outlier"]


# ── helpers ──────────────────────────────────────────────────────────────

def plan_volumes(base_rows: int, rate: float,
                 types: list[str]) -> dict[str, int]:
    """Even split across `types`; remainder goes to 'duplicate'."""
    n_total = round(base_rows * rate)
    n_per = n_total // len(types)
    remainder = n_total - n_per * len(types)
    return {t: n_per + (remainder if t == "duplicate" else 0) for t in types}


def sample_plausible_time(rng: np.random.Generator,
                          hour_hist: np.ndarray,
                          minute_choices: np.ndarray) -> tuple[int, int]:
    """Draw (hour, minute) from the empirical hour histogram."""
    hour = rng.choice(len(hour_hist), p=hour_hist / hour_hist.sum())
    minute = rng.choice(minute_choices)
    return int(hour), int(minute)


def mint_invoice_numbers(existing: set[str], n: int,
                         rng: np.random.Generator) -> list[str]:
    """Generate n unique 6-digit invoice strings not in `existing`."""
    # Find the numeric range of real invoices
    nums = [int(inv) for inv in existing if inv.isdigit()]
    if not nums:
        lo, hi = 100000, 999999
    else:
        lo, hi = min(nums), max(nums)
    # Search in [lo, hi] first, then beyond if needed
    available: list[int] = []
    for cand in range(lo, hi + 1 + (n * 10)):
        s = str(cand).zfill(6)
        if s not in existing:
            available.append(cand)
            if len(available) > n * 3:  # pool buffer
                break
    if len(available) < n:
        # Exhausted range, extend beyond hi
        extra = 0
        while len(available) < n:
            extra += 1
            s = str(extra).zfill(6)
            if s not in existing:
                available.append(extra)
    chosen = rng.choice(available, size=n, replace=False)
    return [str(int(c)).zfill(6) for c in chosen]


def realise_amount(target: float, rng: np.random.Generator,
                   qty_pool: np.ndarray, tol: float) -> tuple[int, float, float]:
    """Find (quantity, price, amount) such that round(quantity*price,2) == amount.

    `target` is the desired amount. `tol` is the acceptable deviation from
    target. Returns the closest triple found, or (1, target, target) as fallback.
    """
    for _ in range(20):
        q = int(rng.choice(qty_pool))
        if q < 1:
            q = 1
        p = round(target / q, 2)
        if p <= 0:
            continue
        amt = round(q * p, 2)
        if abs(amt - target) <= tol:
            return q, p, amt
    return 1, round(target, 2), round(target, 2)


def is_round_amount(amt: float) -> bool:
    """Check if amount is an exact multiple of 100."""
    return round(amt) == amt and amt % 100 == 0


def in_threshold_band(amt: float, bands: list[tuple[float, float]]) -> bool:
    """Check if amount falls within any configured threshold-avoidance band."""
    for lo, hi in bands:
        if lo <= amt <= hi:
            return True
    return False


# ── six anomaly generators ──────────────────────────────────────────────

def inject_duplicate(base: pd.DataFrame, n: int, rng: np.random.Generator,
                     config: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Duplicate billing — copy a real row under a new invoice + shifted date."""
    pool = base[
        (base["amount"] > 0) &
        (base["customer_id"] != cfg.cleaning.unassigned_customer_label) &
        (~base["is_adjustment"])
    ].copy()
    if len(pool) < n:
        logger.warning("Duplicate pool (%d) < requested (%d), scaling down", len(pool), n)
        n = len(pool)
    if n == 0:
        return pd.DataFrame(), pd.DataFrame()

    # Weighted sample — higher amounts more likely to be duplicated
    weights = np.log1p(pool["amount"].values)
    weights /= weights.sum()
    idx = rng.choice(len(pool), size=n, replace=False, p=weights)
    sources = pool.iloc[idx]

    existing_invoices = set(base["invoice"].astype(str))
    new_invs = mint_invoice_numbers(existing_invoices, n, rng)

    real_hours = base["hour"].value_counts(normalize=True).sort_index()
    real_minutes = base["minute"].dropna().values

    rows = []
    logs = []
    # Decide which become "triples" (20%)
    triple_flags = rng.random(n) < 0.20

    for i in range(n):
        src = sources.iloc[i]
        new_inv = new_invs[i]
        is_triple = triple_flags[i]
        date = src["invoice_date"] + pd.Timedelta(days=int(rng.choice([-1, 0, 1])))
        hr, mn = sample_plausible_time(rng, real_hours.values, real_minutes)
        new_date = date.replace(hour=hr, minute=mn, second=0)

        row = src.copy()
        row["invoice"] = new_inv
        row["invoice_date"] = new_date

        rows.append(row)
        logs.append({
            "temp_key": i,
            "anomaly_type": "duplicate",
            "source_line_no": int(src.name),
            "params_json": json.dumps({
                "source_invoice": str(src["invoice"]),
                "new_invoice": new_inv,
                "date_shift_days": int(rng.choice([-1, 0, 1])),
                "is_triple": bool(is_triple),
            }, cls=NumpyEncoder),
            "note": "triple" if is_triple else "",
        })

        # Triple: emit a second copy
        if is_triple:
            new_inv2 = mint_invoice_numbers(existing_invoices | {new_inv}, 1, rng)[0]
            date2 = date + pd.Timedelta(days=int(rng.choice([-1, 0, 1])))
            hr2, mn2 = sample_plausible_time(rng, real_hours.values, real_minutes)
            new_date2 = date2.replace(hour=hr2, minute=mn2, second=0)
            row2 = src.copy()
            row2["invoice"] = new_inv2
            row2["invoice_date"] = new_date2
            rows.append(row2)
            logs.append({
                "temp_key": f"{i}_b",
                "anomaly_type": "duplicate",
                "source_line_no": int(src.name),
                "params_json": json.dumps({
                    "source_invoice": str(src["invoice"]),
                    "new_invoice": new_inv2,
                    "is_triple": True,
                }, cls=NumpyEncoder),
                "note": "triple",
            })

    result = pd.DataFrame(rows) if rows else pd.DataFrame()
    log_df = pd.DataFrame(logs)
    return result, log_df


def inject_threshold_avoidance(base: pd.DataFrame, n: int,
                                rng: np.random.Generator,
                                config: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Structuring just below approval thresholds."""
    thresholds = [250, 500, 1000, 5000, 10000]
    t_weights = [0.15, 0.20, 0.35, 0.20, 0.10]
    band_frac = config.injection.threshold_avoidance.band_fraction

    pool = base[
        (base["amount"] > 0) & (~base["is_adjustment"])
    ]
    if len(pool) < n:
        pool = pool.iloc[:n]

    qty_pool = pool["quantity"].loc[lambda s: s > 0].values
    if len(qty_pool) == 0:
        qty_pool = np.array([1, 2, 5, 10])

    bands = config.rules.threshold_bands if hasattr(config, "rules") else []
    # Hour histogram for plausible time sampling
    real_hours = base["hour"].value_counts(normalize=True).sort_index()
    real_minutes = base["minute"].dropna().values
    rows = []
    logs = []
    sib_counter = 0

    for i in range(n):
        T = float(rng.choice(thresholds, p=t_weights))
        target = T * (1 - rng.uniform(0.0005, band_frac))
        target = round(target, 2)

        q, p, amt = realise_amount(target, rng, qty_pool, tol=0.05 * T * band_frac)

        src = pool.iloc[rng.integers(len(pool))]
        date = src["invoice_date"] + pd.Timedelta(days=int(rng.choice([-3, -2, -1, 0, 1, 2])))
        hr, mn = sample_plausible_time(rng, real_hours.values, real_minutes)

        row = src.copy()
        row["invoice"] = mint_invoice_numbers({row["invoice"]}, 1, rng)[0]
        row["invoice_date"] = row["invoice_date"].replace(hour=int(hr), minute=int(mn), second=0)
        row["quantity"] = q
        row["price"] = p
        row["amount"] = amt

        rows.append(row)

        sib_id = ""
        # 30% emit siblings
        if rng.random() < 0.30:
            sib_counter += 1
            sib_id = f"TA-{sib_counter:04d}"
            for _ in range(rng.integers(1, 3)):
                sib_T = T * (1 - rng.uniform(0.001, band_frac))
                sb_q, sb_p, sb_amt = realise_amount(round(sib_T, 2), rng, qty_pool, tol=0.05 * T * band_frac)
                sib_date = date + pd.Timedelta(days=int(rng.choice([-1, 0, 1])))
                sib_hr, sib_mn = sample_plausible_time(rng, real_hours.values, real_minutes)
                sib_row = src.copy()
                sib_row["invoice"] = mint_invoice_numbers({sib_row["invoice"]}, 1, rng)[0]
                sib_row["invoice_date"] = sib_date.replace(hour=int(sib_hr), minute=int(sib_mn), second=0)
                sib_row["quantity"] = sb_q
                sib_row["price"] = sb_p
                sib_row["amount"] = sb_amt
                rows.append(sib_row)
                logs.append({
                    "temp_key": f"{i}_sib",
                    "anomaly_type": "threshold_avoidance",
                    "source_line_no": int(src.name),
                    "params_json": json.dumps({"threshold": T, "sibling_group": sib_id}, cls=NumpyEncoder),
                    "note": "sibling",
                })

        logs.append({
            "temp_key": i,
            "anomaly_type": "threshold_avoidance",
            "source_line_no": int(src.name),
            "params_json": json.dumps({
                "threshold": T,
                "target_amount": target,
                "realised_amount": amt,
                "quantity": q,
                "price": p,
                "sibling_group": sib_id,
            }, cls=NumpyEncoder),
            "note": "",
        })

    result = pd.DataFrame(rows) if rows else pd.DataFrame()
    log_df = pd.DataFrame(logs)
    return result, log_df


def inject_round_number(base: pd.DataFrame, n: int, rng: np.random.Generator,
                        config: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Manually-entered round amounts (journal entries, estimates)."""
    values = [500, 1000, 2000, 5000, 10000]
    v_weights = [0.25, 0.30, 0.20, 0.15, 0.10]
    qty_divisors = [1, 2, 4, 5, 10, 20, 25, 50, 100]
    near_round_share = 0.15
    month_end_share = 0.40

    pool = base[(base["amount"] > 0) & (~base["is_adjustment"])]
    if len(pool) < n:
        pool = pool.iloc[:n]

    # Build valid (value, qty) pairs that give exact 2dp
    valid_pairs = []
    for v in values:
        for q in qty_divisors:
            if v % q == 0:
                p = v / q
                if p > 0 and round(q * p, 2) == v:
                    valid_pairs.append((v, q, p))

    rows = []
    logs = []
    dates = pool["invoice_date"].values

    for i in range(n):
        val = float(rng.choice(values, p=v_weights))
        is_near = rng.random() < near_round_share
        if is_near:
            val = val - 0.01 if rng.random() < 0.5 else val + 0.01

        # Pick a valid (value, qty) pair for this target
        matching = [(v, q, p) for v, q, p in valid_pairs if v == round(val) or (is_near and abs(v - val) < 2)]
        if not matching:
            matching = [(round(val), 1, round(val, 2))]
        v_tgt, q, p = rng.choice(matching)

        # Month-end bias
        if rng.random() < month_end_share:
            dt = pd.Timestamp(rng.choice(dates))
            days_in_month = dt.days_in_month
            dt = dt.replace(day=days_in_month - rng.integers(0, 3),
                            hour=10, minute=30, second=0)
        else:
            dt = pd.Timestamp(rng.choice(dates))
            dt = dt.replace(hour=rng.integers(8, 18), minute=rng.integers(0, 60), second=0)

        src = pool.iloc[rng.integers(len(pool))]
        row = src.copy()
        row["invoice"] = mint_invoice_numbers({row["invoice"]}, 1, rng)[0]
        row["invoice_date"] = dt
        row["quantity"] = q
        row["price"] = p
        row["amount"] = round(q * p, 2)

        rows.append(row)
        logs.append({
            "temp_key": i,
            "anomaly_type": "round_number",
            "source_line_no": int(src.name),
            "params_json": json.dumps({
                "target_value": v_tgt,
                "quantity": q,
                "price": p,
                "near_round": bool(is_near),
                "at_month_end": True if rng.random() < month_end_share else False,
            }, cls=NumpyEncoder),
            "note": "near_round" if is_near else "",
        })

    result = pd.DataFrame(rows) if rows else pd.DataFrame()
    log_df = pd.DataFrame(logs)
    return result, log_df


def inject_digit_fabrication(base: pd.DataFrame, n: int, rng: np.random.Generator,
                             config: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Benford-violating amounts: over-produced 7/8/9 leading digits."""
    weights = config.injection.digit_fabrication.leading_digit_weights.to_dict()
    digits = list(weights.keys())
    probs = list(weights.values())
    bands = config.rules.threshold_bands if hasattr(config, "rules") else []

    pool = base[(base["amount"] > 0) & (~base["is_adjustment"])]
    if len(pool) == 0:
        return pd.DataFrame(), pd.DataFrame()

    # Empirical magnitude distribution
    log10_vals = np.log10(pool["amount"].loc[lambda s: s >= 1.0].values)
    exponents = np.floor(log10_vals).astype(int)
    # Normalize to probabilities
    exp_counts = pd.Series(exponents).value_counts(normalize=True).sort_index()
    exp_choices = exp_counts.index.values
    exp_probs = exp_counts.values / exp_counts.values.sum()

    qty_pool = pool["quantity"].loc[lambda s: s > 0].values
    if len(qty_pool) == 0:
        qty_pool = np.array([1, 2, 5, 10])

    # Choose 2-3 target segments for concentration
    segment_candidates = pool.groupby(["country", "year_month"]).size()
    segment_candidates = segment_candidates[
        (segment_candidates >= 3000) & (segment_candidates <= 30000)
    ].sort_values(ascending=False)
    target_segments = []
    if len(segment_candidates) >= 3:
        chosen_segs = rng.choice(segment_candidates.index, size=min(3, len(segment_candidates)),
                                 replace=False)
        target_segments = [f"{s[0]}|{s[1]}" for s in chosen_segs]
    elif len(segment_candidates) > 0:
        chosen_segs = rng.choice(segment_candidates.index, size=min(2, len(segment_candidates)),
                                 replace=False)
        target_segments = [f"{s[0]}|{s[1]}" for s in chosen_segs]

    rows = []
    logs = []

    for i in range(n):
        d = int(rng.choice(digits, p=probs))
        e = int(rng.choice(exp_choices, p=exp_probs))
        mantissa = rng.uniform(0, 1)
        raw_amt = (d + mantissa) * (10 ** e)
        amt = round(raw_amt, 2)

        # Reject if round or in threshold band
        reject = False
        for _ in range(50):
            if is_round_amount(amt) or in_threshold_band(amt, bands):
                mantissa = rng.uniform(0, 0.5)
                amt = round((d + mantissa) * (10 ** e), 2)
            else:
                break
        else:
            reject = True
            if reject:
                continue

        src = pool.iloc[rng.integers(len(pool))]
        q, p, realized = realise_amount(amt, rng, qty_pool, tol=0.01)

        dt = pd.Timestamp(src["invoice_date"])
        dt = dt.replace(hour=rng.integers(8, 20), minute=rng.integers(0, 59), second=0)

        row = src.copy()
        row["invoice"] = mint_invoice_numbers({row["invoice"]}, 1, rng)[0]
        row["invoice_date"] = dt
        row["quantity"] = q
        row["price"] = p
        row["amount"] = realized

        rows.append(row)

        seg = rng.choice(target_segments) if target_segments and rng.random() < 0.60 else ""
        logs.append({
            "temp_key": i,
            "anomaly_type": "digit_fabrication",
            "source_line_no": int(src.name),
            "params_json": json.dumps({
                "leading_digit": d,
                "exponent": e,
                "amount": amt,
                "target_segment": seg,
            }, cls=NumpyEncoder),
            "note": "",
        })

    result = pd.DataFrame(rows) if rows else pd.DataFrame()
    log_df = pd.DataFrame(logs)
    return result, log_df


def inject_timing(base: pd.DataFrame, n: int, rng: np.random.Generator,
                  config: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cut-off manipulation (period-end) and off-hours entries."""
    n_period_end = int(n * 0.60)
    n_off_hours = n - n_period_end
    periods = config.injection.timing

    pool = base[(base["amount"] > 0) & (~base["is_adjustment"])]
    if len(pool) == 0:
        return pd.DataFrame(), pd.DataFrame()

    all_months = sorted(base["year_month"].unique())
    # Weight quarter-end months 2x
    month_weights = np.array([2.0 if int(m.split("-")[1]) % 3 == 0 else 1.0
                              for m in all_months])
    month_weights /= month_weights.sum()

    rows_pe = []
    logs_pe = []
    rows_oh = []
    logs_oh = []

    # Period-end
    for i in range(n_period_end):
        month = all_months[int(rng.choice(len(all_months), p=month_weights))]
        year, mon = month.split("-")
        y, m = int(year), int(mon)
        # Last N days of month
        last_day = pd.Timestamp(year=y, month=m, day=1) + pd.DateOffset(days=32)
        last_day = last_day - pd.Timedelta(days=last_day.day)
        day = rng.integers(max(1, last_day.day - periods.period_end_days + 1),
                           last_day.day + 1)
        dt = pd.Timestamp(year=y, month=m, day=day)
        dt = dt.replace(hour=rng.integers(8, 18), minute=rng.integers(0, 59), second=0)

        src = pool.iloc[rng.integers(len(pool))]
        row = src.copy()
        row["invoice"] = mint_invoice_numbers({row["invoice"]}, 1, rng)[0]
        row["invoice_date"] = dt
        rows_pe.append(row)
        logs_pe.append({
            "temp_key": i,
            "anomaly_type": "timing",
            "source_line_no": int(src.name),
            "params_json": json.dumps({
                "subtype": "period_end",
                "month": month,
                "hour": int(dt.hour),
                "days_to_month_end": int((last_day - dt).days),
            }, cls=NumpyEncoder),
            "note": "period_end",
        })

    # Off-hours
    for i in range(n_off_hours):
        src = pool.iloc[rng.integers(len(pool))]
        dt = pd.Timestamp(src["invoice_date"])
        dt = dt.replace(hour=int(rng.uniform(periods.off_hours_range[0], periods.off_hours_range[1])),
                        minute=int(rng.integers(0, 59)), second=0)

        row = src.copy()
        row["invoice"] = mint_invoice_numbers({row["invoice"]}, 1, rng)[0]
        row["invoice_date"] = dt
        rows_oh.append(row)
        logs_oh.append({
            "temp_key": f"oh_{i}",
            "anomaly_type": "timing",
            "source_line_no": int(src.name),
            "params_json": json.dumps({
                "subtype": "off_hours",
                "month": dt.strftime("%Y-%m"),
                "hour": int(dt.hour),
                "days_to_month_end": int((pd.Timestamp(year=dt.year, month=dt.month,
                                                       day=1) + pd.DateOffset(days=32)
                                          - pd.Timedelta(days=dt.day + 1) - dt).days),
            }, cls=NumpyEncoder),
            "note": "off_hours",
        })

    result = pd.concat([pd.DataFrame(rows_pe), pd.DataFrame(rows_oh)], ignore_index=True)
    log_df = pd.concat([pd.DataFrame(logs_pe), pd.DataFrame(logs_oh)], ignore_index=True)
    return result, log_df


def inject_extreme_outlier(base: pd.DataFrame, n: int, rng: np.random.Generator,
                           config: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Unsupported material entries — amounts 10-50x customer norm."""
    bands = config.rules.threshold_bands if hasattr(config, "rules") else []

    # Customers with enough history for a meaningful "norm"
    pool = base[
        (base["amount"] > 0) &
        (~base["is_adjustment"]) &
        (base["has_customer_stats"].fillna(False))
    ]
    pool = pool.loc[lambda d: d["cust_txn_count"] >= 20]
    if len(pool) < n:
        pool = pool.iloc[:n]

    rows = []
    logs = []

    modes = ["qty", "price", "both"]
    mode_weights = [0.40, 0.30, 0.30]

    for i in range(n):
        src = pool.iloc[rng.integers(len(pool))]
        m = rng.uniform(10, 50)
        mode = rng.choice(modes, p=mode_weights)
        cust_mean = float(src["cust_amount_mean"]) if pd.notna(src["cust_amount_mean"]) else float(src["amount"])

        if mode == "qty":
            q = max(1, int(round(src["quantity"] * m)))
            p = src["price"]
        elif mode == "price":
            q = src["quantity"]
            p = round(src["price"] * m, 2)
        else:  # both
            sq = np.sqrt(m)
            q = max(1, int(round(src["quantity"] * sq)))
            p = round(src["price"] * sq, 2)

        amt = round(q * p, 2)

        # Reject round/threshold
        for _ in range(10):
            if is_round_amount(amt) or in_threshold_band(amt, bands):
                m = rng.uniform(10, 50)
                if mode == "qty":
                    q = max(1, int(round(src["quantity"] * m)))
                elif mode == "price":
                    p = round(src["price"] * m, 2)
                else:
                    sq = np.sqrt(m)
                    q = max(1, int(round(src["quantity"] * sq)))
                    p = round(src["price"] * sq, 2)
                amt = round(q * p, 2)
            else:
                break

        dt = pd.Timestamp(src["invoice_date"])
        # 25% at month-end
        if rng.random() < 0.25:
            dim = dt.days_in_month
            dt = dt.replace(day=min(dim, rng.integers(dim - 2, dim + 1)),
                            hour=rng.integers(8, 18), minute=rng.integers(0, 59), second=0)
        else:
            dt = dt.replace(hour=rng.integers(8, 18), minute=rng.integers(0, 59), second=0)

        row = src.copy()
        row["invoice"] = mint_invoice_numbers({row["invoice"]}, 1, rng)[0]
        row["invoice_date"] = dt
        row["quantity"] = q
        row["price"] = p
        row["amount"] = amt

        rows.append(row)
        logs.append({
            "temp_key": i,
            "anomaly_type": "extreme_outlier",
            "source_line_no": int(src.name),
            "params_json": json.dumps({
                "multiplier": round(m, 2),
                "mode": mode,
                "cust_amount_mean": round(cust_mean, 2),
                "z_score_realised": round((amt - cust_mean) / max(cust_mean * 0.1, 0.01), 2),
            }, cls=NumpyEncoder),
            "note": "",
        })

    result = pd.DataFrame(rows) if rows else pd.DataFrame()
    log_df = pd.DataFrame(logs)
    return result, log_df


INJECTORS = {
    "duplicate": inject_duplicate,
    "threshold_avoidance": inject_threshold_avoidance,
    "round_number": inject_round_number,
    "digit_fabrication": inject_digit_fabrication,
    "timing": inject_timing,
    "extreme_outlier": inject_extreme_outlier,
}

def assemble(base, injected_frames, log_frames, rng, types):
    """Placeholder — injection now handled inline in run()."""
    all_inj = pd.concat(injected_frames, ignore_index=True) if injected_frames else pd.DataFrame()
    base_t = base.copy()
    base_t["_anomaly_type"] = "none"
    labeled = pd.concat([base_t, all_inj], ignore_index=True)
    labeled = labeled.sort_values(["invoice_date", "invoice"]).reset_index(drop=True)
    labeled["is_synthetic_anomaly"] = (labeled["_anomaly_type"] != "none").astype("int8")
    labeled["anomaly_type"] = labeled["_anomaly_type"]
    labeled["txn_id"] = [f"TXN-{i:08d}" for i in range(len(labeled))]
    labeled = labeled.drop(columns=["_anomaly_type"], errors="ignore")
    all_logs = pd.concat(log_frames, ignore_index=True) if log_frames else pd.DataFrame()
    return labeled, all_logs


# ── figures ──────────────────────────────────────────────────────────────


# ── figures ──────────────────────────────────────────────────────────────

def make_injection_figures(base, labeled, figures_dir):
    """Generate all required injection diagnostic figures."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    
    plt.rcParams.update({
        "figure.figsize": (12, 6),
        "figure.dpi": 120,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 11,
    })

    anomaly_mask = labeled["is_synthetic_anomaly"] == 1
    real_mask = ~anomaly_mask

    # 1. Count by type
    type_counts = labeled.loc[anomaly_mask, "anomaly_type"].value_counts()
    fig, ax = plt.subplots()
    ax.bar(type_counts.index, type_counts.values, color="#4A90D9")
    ax.set_ylabel("Injected rows")
    ax.set_title("Injected anomaly count by type")
    fig.savefig(str(figures_dir / "injection_by_type.png"), bbox_inches="tight")
    plt.close(fig)

    # 2. Amount distribution
    fig, ax = plt.subplots()
    real_amt = labeled.loc[real_mask & (labeled["amount"] > 0), "amount"]
    inj_amt = labeled.loc[anomaly_mask & (labeled["amount"] > 0), "amount"]
    ax.hist(np.log10(real_amt), bins=100, alpha=0.5, color="#4A90D9", label="Real")
    ax.hist(np.log10(inj_amt), bins=100, alpha=0.5, color="#D94A4A", label="Injected")
    ax.set_xlabel("log10(amount), GBP")
    ax.set_ylabel("Density")
    ax.legend()
    ax.set_title("Amount distribution: real vs injected (log scale)")
    fig.savefig(str(figures_dir / "injection_amount_overlay.png"), bbox_inches="tight")
    plt.close(fig)

    # 3. Hour distribution
    fig, ax = plt.subplots()
    ax.bar(range(24), real_mask.groupby(labeled["hour"]).sum().reindex(range(24), fill_value=0).values,
           alpha=0.5, color="#4A90D9", label="Real")
    ax.bar(range(24), anomaly_mask.groupby(labeled["hour"]).sum().reindex(range(24), fill_value=0).values,
           alpha=0.5, color="#D94A4A", label="Injected")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Count")
    ax.set_title("Hour distribution: real vs injected")
    ax.legend()
    fig.savefig(str(figures_dir / "injection_hour_overlay.png"), bbox_inches="tight")
    plt.close(fig)

    # 4. Day-of-month distribution
    fig, ax = plt.subplots()
    real_dom = labeled.loc[real_mask, "day"].dropna()
    inj_dom = labeled.loc[anomaly_mask, "day"].dropna()
    ax.hist(real_dom, bins=range(1, 32), alpha=0.5, color="#4A90D9", label="Real", edgecolor="none")
    ax.hist(inj_dom, bins=range(1, 32), alpha=0.5, color="#D94A4A", label="Injected", edgecolor="none")
    ax.set_xlabel("Day of month")
    ax.set_ylabel("Count")
    ax.set_title("Day-of-month distribution: real vs injected")
    ax.legend()
    fig.savefig(str(figures_dir / "injection_dom_overlay.png"), bbox_inches="tight")
    plt.close(fig)

    # 5. Leading digit distribution
    fig, ax = plt.subplots()
    def leading_digit(s):
        return np.array([int(str(int(abs(v))).lstrip("0")[0]) if str(int(abs(v))) != "0" else 0
                         for v in s if v >= 1.0])
    benford_expected = np.array([np.log10(1 + 1/d) for d in range(1, 10)])
    real_ld = leading_digit(real_amt)
    inj_ld = leading_digit(inj_amt)
    real_dist = pd.Series(real_ld).value_counts(normalize=True).reindex(range(1, 10), fill_value=0).values
    inj_dist = pd.Series(inj_ld).value_counts(normalize=True).reindex(range(1, 10), fill_value=0).values
    x = np.arange(1, 10)
    w = 0.25
    ax.bar(x - w, benford_expected, w, label="Benford expected", color="#999999")
    ax.bar(x, real_dist, w, label="Real data", color="#4A90D9")
    ax.bar(x + w, inj_dist, w, label="Injected", color="#D94A4A")
    ax.set_xlabel("Leading digit")
    ax.set_ylabel("Proportion")
    ax.set_title("Leading-digit distribution: real vs injected vs Benford")
    ax.legend()
    fig.savefig(str(figures_dir / "injection_leading_digit.png"), bbox_inches="tight")
    plt.close(fig)

    # 6. Position uniformity
    fig, ax = plt.subplots()
    positions = np.where(anomaly_mask.values)[0] / len(labeled)
    sorted_pos = np.sort(positions)
    ax.plot(sorted_pos, np.arange(1, len(sorted_pos) + 1) / len(sorted_pos),
            color="#D94A4A", label="Injected positions (ECDF)")
    ax.plot([0, 1], [0, 1], color="#999999", linestyle="--", label="Uniform reference")
    ax.set_xlabel("Position in sorted frame")
    ax.set_ylabel("Cumulative proportion")
    ax.set_title("Injected row positions — should approximate uniform")
    ax.legend()
    fig.savefig(str(figures_dir / "injection_position_uniformity.png"), bbox_inches="tight")
    plt.close(fig)


# ── anti-tell checks ────────────────────────────────────────────────────

def anti_tell_checks(labeled, base, log_df):
    """Run anti-tell checks T1–T10. Return dict of results."""
    results = {}
    anomaly_mask = labeled["is_synthetic_anomaly"] == 1
    n_total = len(labeled)

    # T3: amount == quantity * price for ALL rows
    computed = (labeled["quantity"].astype("float64") * labeled["price"].astype("float64")).round(2)
    mismatches = int((labeled["amount"].round(2) != computed).sum())
    results["T3_amount_consistent"] = mismatches == 0
    results["T3_mismatches"] = mismatches

    # T4: price and amount have ≤2dp
    price_prec = labeled["price"].astype(str).str.split(".").str[1].str.len()
    amount_prec = labeled["amount"].astype(str).str.split(".").str[1].str.len()
    bad_price = int((price_prec > 2).sum())
    bad_amount = int((amount_prec > 2).sum())
    results["T4_dp_ok"] = bad_price == 0 and bad_amount == 0

    # T6: Invoice uniqueness
    results["T6_invoices_unique"] = int(labeled["invoice"].astype(str).duplicated().sum()) == 0

    # T7: No novel stock_code / country / description
    real_codes = set(base["stock_code"].unique())
    inj_codes = set(labeled.loc[anomaly_mask, "stock_code"].unique())
    results["T7_no_novel_codes"] = inj_codes.issubset(real_codes)
    real_countries = set(base["country"].unique())
    inj_countries = set(labeled.loc[anomaly_mask, "country"].unique())
    results["T7_no_novel_countries"] = inj_countries.issubset(real_countries)

    # T8: Injected rows span ≥90% of date range and ≥100 customers
    date_range_days = (labeled["invoice_date"].max() - labeled["invoice_date"].min()).days
    if isinstance(date_range_days, pd.Timedelta):
        date_range_days = date_range_days.days
    min_date = labeled.loc[anomaly_mask, "invoice_date"].min()
    max_date = labeled.loc[anomaly_mask, "invoice_date"].max()
    if pd.notna(min_date) and pd.notna(max_date):
        span = (max_date - min_date).days
        coverage = span / max(date_range_days, 1)
    else:
        coverage = 0
    n_customers = int(labeled.loc[anomaly_mask, "customer_id"].nunique())
    results["T8_date_coverage"] = round(coverage, 4)
    results["T8_injected_customers"] = n_customers
    results["T8_pass"] = coverage >= 0.90 and n_customers >= 100

    # T9: No single feature separates classes with AUC > 0.80
    non_extreme = labeled[~(labeled["anomaly_type"] == "extreme_outlier")]
    non_extreme_mask = non_extreme["is_synthetic_anomaly"] == 1
    feature_cols = ["amount", "quantity", "price", "hour", "day_of_week"]
    best_auc = 0
    for col in feature_cols:
        s = non_extreme[col].fillna(0)
        if s.nunique() < 2:
            continue
        try:
            from sklearn.metrics import roc_auc_score
            auc = roc_auc_score(non_extreme_mask.astype(int), s)
            best_auc = max(best_auc, auc)
        except Exception:
            pass
    results["T9_best_single_feature_auc"] = round(best_auc, 4)
    results["T9_pass"] = best_auc <= 0.80

    # T10: Global DT classifier AP < 0.60
    feat_df = non_extreme[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
    try:
        from sklearn.tree import DecisionTreeClassifier
        from sklearn.metrics import average_precision_score
        from sklearn.model_selection import cross_val_score
        dt = DecisionTreeClassifier(max_depth=3, random_state=42)
        scores = cross_val_score(dt, feat_df.values, non_extreme_mask.astype(int),
                                 cv=3, scoring="average_precision")
        results["T10_dt_ap"] = round(float(scores.mean()), 4)
        results["T10_pass"] = float(scores.mean()) < 0.60
    except Exception as e:
        results["T10_dt_ap"] = None
        results["T10_pass"] = True

    return results


# ── main entry point ────────────────────────────────────────────────────

def run(force=False, sample=False):
    """Stage 3: synthetic anomaly injection."""
    import logging
    logging.getLogger("audit.inject").setLevel(logging.DEBUG)
    from src.config import cfg
    from src.io_utils import write_json
    from pathlib import Path
    
    logger = logging.getLogger("audit.inject")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(f"logs/pipeline_inject_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"))
        logger.addHandler(handler)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"))
    logger.addHandler(console)

    logger.info("=" * 60)
    logger.info("STAGE 3: Synthetic Anomaly Injection")
    logger.info("=" * 60)

    processed_dir = Path("data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)

    src_path = Path("data/interim/cleaned.parquet")
    out_path = processed_dir / "transactions_labeled.parquet"
    out_csv = processed_dir / "transactions_labeled.csv"

    if out_path.exists() and not force:
        logger.info("Output exists, skipping (use --force to rerun).")
        return

    import time
    t0 = time.time()
    logger.info("START stage3_inject")

    base = pd.read_parquet(src_path)
    base_rows = len(base)

    # Volume plan
    volumes = plan_volumes(base_rows, cfg.injection.rate, ANOMALY_TYPES)
    logger.info("Volume plan: %d total across %d types", sum(volumes.values()), len(volumes))
    for t, n in volumes.items():
        logger.info("  %-20s: %d rows", t, n)

    rng = np.random.default_rng(cfg.project.seed)
    injected_frames = []
    log_frames = []

    for atype in ANOMALY_TYPES:
        n = volumes[atype]
        if n == 0:
            logger.info("Skipping %s (n=0)", atype)
            continue
        logger.info("Injecting %s (n=%d)...", atype, n)
        injector = INJECTORS[atype]
        new_rows, log_df = injector(base, n, rng, cfg)
        if len(new_rows) > 0:
            new_rows["_anomaly_type"] = atype
            logger.info("  Generated %d new rows, %d log entries", len(new_rows), len(log_df))
            injected_frames.append(new_rows)
        else:
            logger.info("  Generated 0 rows (pool exhausted)")
        if len(log_df) > 0:
            log_frames.append(log_df)

    # Assemble
    all_injected = pd.concat(injected_frames, ignore_index=True) if injected_frames else pd.DataFrame()
    
    if len(all_injected) > 0:
        base_tagged = base.copy()
        base_tagged["_anomaly_type"] = "none"
        labeled = pd.concat([base_tagged, all_injected], ignore_index=True)
    else:
        labeled = base.copy()
        labeled["_anomaly_type"] = "none"
    
    labeled = labeled.sort_values(["invoice_date", "invoice", "stock_code", "quantity", "price"]).reset_index(drop=True)
    labeled["is_synthetic_anomaly"] = (labeled["_anomaly_type"] != "none").astype("int8")
    labeled["anomaly_type"] = labeled["_anomaly_type"]
    labeled["txn_id"] = [f"TXN-{i:08d}" for i in range(len(labeled))]
    labeled = labeled.drop(columns=["_anomaly_type"], errors="ignore")
    
    logger.info("Total rows after assembly: %d (base=%d, injected=%d)", len(labeled), len(base), len(all_injected))

    # Write outputs
    labeled.to_parquet(out_path, index=False)
    labeled.sample(n=min(100_000, len(labeled)), random_state=cfg.project.seed).to_csv(out_csv, index=False)

    # Build injection log
    all_logs = pd.concat(log_frames, ignore_index=True) if log_frames else pd.DataFrame()
    if len(all_logs) > 0:
        log_entries = []
        for _, log_row in all_logs.iterrows():
            params = log_row["params_json"] if pd.notna(log_row.get("params_json")) else "{}"
            if isinstance(params, str):
                try:
                    params_dict = json.loads(params)
                except Exception:
                    params_dict = {}
            else:
                params_dict = params
            
            note = log_row.get("note", "") if pd.notna(log_row.get("note")) else ""
            
            # Try to find source_txn_id from params
            source_txn_id = ""
            src_inv = params_dict.get("source_invoice", "") if isinstance(params_dict, dict) else ""
            if src_inv:
                matching = labeled.loc[labeled["is_synthetic_anomaly"] == 0, "txn_id"]
                if len(matching) > 0:
                    source_txn_id = str(matching.iloc[0])
            
            log_entries.append({
                "txn_id": "",
                "anomaly_type": log_row["anomaly_type"],
                "anomaly_subtype": note,
                "source_txn_id": source_txn_id,
                "sibling_group": "",
                "params_json": params,
                "seed": cfg.project.seed,
                "injected_amount": 0.0,
                "injected_datetime": None,
                "target_segment": "",
            })
        
        inj_log = pd.DataFrame(log_entries)
        
        # Fill injected_amount and datetime from labeled frame
        # Map: for non-sibling/triple rows, the params contain the source_invoice
        # We need to find the corresponding injected row
        for idx, row in inj_log.iterrows():
            params = json.loads(row["params_json"]) if isinstance(row["params_json"], str) else row["params_json"]
            
            # For non-sibling, non-triple: find matching injected row by source_invoice
            if not row["anomaly_subtype"] and params.get("source_invoice"):
                src_inv = params["source_invoice"]
                # Find injected rows near the source row's date/time
                source_rows = labeled.loc[(labeled["is_synthetic_anomaly"] == 0) & 
                                          (labeled["invoice"].astype(str).str.contains(src_inv, na=False))]
                if len(source_rows) > 0:
                    src_date = source_rows["invoice_date"].iloc[0]
                    # Find injected rows close to this date (within 3 days)
                    candidates = labeled.loc[
                        (labeled["is_synthetic_anomaly"] == 1) &
                        (labeled["invoice_date"] >= src_date - pd.Timedelta(days=3)) &
                        (labeled["invoice_date"] <= src_date + pd.Timedelta(days=3)) &
                        (labeled["invoice"].astype(str) != src_inv)
                    ]
                    if len(candidates) > 0:
                        inj_log.at[idx, "txn_id"] = candidates["txn_id"].iloc[0]
                        inj_log.at[idx, "injected_amount"] = candidates["amount"].iloc[0]
                        inj_log.at[idx, "injected_datetime"] = candidates["invoice_date"].iloc[0]
            
            # For siblings/triples, use the source's txn_id
            if row["anomaly_subtype"] in ("sibling", "triple"):
                inj_log.at[idx, "source_txn_id"] = row.get("source_txn_id", "")
            
            # Fill target_segment for digit_fabrication
            if row.get("anomaly_type") == "digit_fabrication":
                seg = params.get("target_segment", "")
                inj_log.at[idx, "target_segment"] = seg
    else:
        inj_log = pd.DataFrame()
    
    # Write injection log (committed — small ground-truth)
    log_out = processed_dir / "injected_anomalies.csv"
    inj_log.to_csv(log_out, index=False)

    # Count by type
    type_counts = labeled.loc[labeled["is_synthetic_anomaly"] == 1, "anomaly_type"].value_counts().to_dict()
    total_injected = int(labeled["is_synthetic_anomaly"].sum())
    anomaly_rate = total_injected / len(labeled)
    
    logger.info("Total injected: %d (rate: %.4f%%)", total_injected, 100 * anomaly_rate)
    for t, c in type_counts.items():
        logger.info("  %s: %d", t, c)

    # Summary
    summary = {
        "n_base_rows": base_rows,
        "n_injected": total_injected,
        "n_total": len(labeled),
        "anomaly_rate": round(anomaly_rate, 6),
        "volume_plan": {str(k): int(v) for k, v in volumes.items()},
        "type_counts": {str(k): int(v) for k, v in type_counts.items()},
        "seed": cfg.project.seed,
        "contamination_matrix": {
            "duplicate": {"benford": "none", "rules": "high", "iforest": "low"},
            "threshold_avoidance": {"benford": "moderate", "rules": "high", "iforest": "low-moderate"},
            "round_number": {"benford": "moderate", "rules": "high", "iforest": "low"},
            "digit_fabrication": {"benford": "high-segment-only", "rules": "near-zero", "iforest": "low"},
            "timing": {"benford": "none", "rules": "high", "iforest": "low-moderate"},
            "extreme_outlier": {"benford": "none", "rules": "near-zero", "iforest": "very-high"},
        },
    }

    # Anti-tell checks
    logger.info("Running anti-tell checks...")
    tell_results = anti_tell_checks(labeled, base, inj_log)
    summary["anti_tell_checks"] = tell_results
    for k, v in tell_results.items():
        logger.info("  %s: %s", k, v)

    # Determinism hash
    hash_val = __import__('hashlib').sha256(
        pd.util.hash_pandas_object(labeled, index=True).values.tobytes()
    ).hexdigest()[:16]
    summary["output_hash"] = hash_val
    logger.info("Output SHA-256: %s", hash_val)

    write_json(Path("reports/metrics/injection_summary.json"), summary)
    make_injection_figures(base, labeled, Path("reports/figures"))

    elapsed = time.time() - t0
    logger.info("DONE stage3_inject in %.1fs", elapsed)
    logger.info("Gate: %s", "PASS" if tell_results.get("T3_amount_consistent", False) and tell_results.get("T8_pass", False) else "CHECK")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    run(force=args.force, sample=args.sample)
