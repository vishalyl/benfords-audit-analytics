"""Shared assertion helpers used by every checks/gate_NN.py script."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


def assert_cols(df: pd.DataFrame, required: set[str]) -> None:
    missing = required - set(df.columns)
    assert not missing, f"Missing required columns: {missing}"


def assert_rowcount(df: pd.DataFrame, expected: int, tol_pct: float = 1.0) -> None:
    actual = len(df)
    tol = expected * tol_pct / 100.0
    assert abs(actual - expected) <= tol, (
        f"Row count {actual} not within {tol_pct}% of expected {expected} "
        f"(tolerance ±{tol:.0f})"
    )


def assert_no_nulls(df: pd.DataFrame, cols: list[str]) -> None:
    nulls = df[cols].isnull().sum()
    bad = nulls[nulls > 0]
    assert bad.empty, f"Null values found in columns: {bad.to_dict()}"


def assert_range(df: pd.DataFrame, col: str, lo, hi) -> None:
    s = df[col]
    bad = s[(s < lo) | (s > hi)]
    assert bad.empty, f"{len(bad)} values in '{col}' outside range [{lo}, {hi}]"


def assert_unique(df: pd.DataFrame, col: str) -> None:
    dup = df[col].duplicated().sum()
    assert dup == 0, f"{dup} duplicate values found in column '{col}'"


def assert_file_exists(path) -> None:
    p = Path(path)
    assert p.exists(), f"Expected file does not exist: {p}"


def _hash_frame(df: pd.DataFrame) -> str:
    return hashlib.sha256(
        pd.util.hash_pandas_object(df, index=True).values.tobytes()
    ).hexdigest()


def assert_deterministic(fn: Callable, *args, runs: int = 2, **kwargs) -> None:
    """Runs fn(*args, **kwargs) `runs` times and asserts identical output hashes."""
    hashes = []
    for _ in range(runs):
        result = fn(*args, **kwargs)
        if isinstance(result, pd.DataFrame):
            hashes.append(_hash_frame(result))
        elif isinstance(result, np.ndarray):
            hashes.append(hashlib.sha256(result.tobytes()).hexdigest())
        else:
            hashes.append(hashlib.sha256(str(result).encode()).hexdigest())
    assert len(set(hashes)) == 1, f"Non-deterministic output across {runs} runs: {hashes}"


def report(title: str, rows: list[tuple]) -> str:
    """Markdown table helper. rows[0] is the header tuple."""
    if not rows:
        return f"### {title}\n\n(no rows)\n"
    header = rows[0]
    body = rows[1:]
    lines = [f"### {title}", "", "| " + " | ".join(str(h) for h in header) + " |",
              "|" + "---|" * len(header)]
    for r in body:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines) + "\n"
