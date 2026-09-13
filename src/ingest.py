"""Stage 0/1, acquire the raw workbook, load, combine, downcast, profile, sample."""
from __future__ import annotations

import argparse
import logging
import time
import zipfile
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
import requests
from tqdm import tqdm

from src.config import COLUMN_RENAME_MAP, cfg
from src.io_utils import write_json
from src.logging_setup import setup_logging, timed

logger = logging.getLogger("audit.ingest")


def download_raw(force: bool = False) -> Path:
    """Ensure data/raw/online_retail_II.xlsx exists. Returns its path."""
    raw_dir = cfg.paths.raw_dir
    xlsx_path = raw_dir / cfg.ingest.excel_filename
    zip_path = raw_dir / "online_retail_II.zip"

    if xlsx_path.exists() and not force:
        logger.info("Raw xlsx already present at %s, skipping download.", xlsx_path)
        return xlsx_path

    if not zip_path.exists() or force:
        url = cfg.ingest.source_url
        logger.info("Downloading %s -> %s", url, zip_path)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            with requests.get(url, stream=True, timeout=120, headers=headers) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0))
                written = 0
                with open(zip_path, "wb") as fh, tqdm(total=total, unit="B", unit_scale=True) as pbar:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        fh.write(chunk)
                        written += len(chunk)
                        pbar.update(len(chunk))
                if total and abs(written - total) > 1024:
                    raise RuntimeError(f"Downloaded {written} bytes, expected {total}")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Failed to download the Online Retail II dataset automatically. "
                "Manually download it from the landing page "
                "https://archive.ics.uci.edu/dataset/502/online+retail+ii and place "
                f"the extracted xlsx at {xlsx_path}. Original error: {exc}"
            ) from exc

    logger.info("Extracting %s", zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        member = next((n for n in zf.namelist() if n.lower().endswith(".xlsx")), None)
        if member is None:
            raise RuntimeError(f"No .xlsx member found inside {zip_path}")
        with zf.open(member) as src, open(xlsx_path, "wb") as dst:
            dst.write(src.read())

    size = xlsx_path.stat().st_size
    assert 35_000_000 <= size <= 60_000_000, f"Unexpected xlsx size: {size} bytes"
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    for sheet in cfg.ingest.sheets:
        assert sheet in wb.sheetnames, f"Expected sheet '{sheet}' not found in {wb.sheetnames}"
    logger.info("Raw xlsx ready at %s (%.1f MB)", xlsx_path, size / 1e6)
    return xlsx_path


def load_sheet(xlsx_path: Path, sheet_name: str) -> pd.DataFrame:
    """Read one sheet with pd.read_excel(engine='openpyxl'). Adds 'source_sheet'."""
    t0 = time.perf_counter()
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name, engine="openpyxl")
    df["source_sheet"] = sheet_name
    logger.info("Loaded sheet '%s': %d rows in %.1fs", sheet_name, len(df), time.perf_counter() - t0)
    return df


def combine_sheets(xlsx_path: Path, sheets: list[str]) -> pd.DataFrame:
    """Read each sheet, concat, rename to canonical columns, add line_no."""
    frames = [load_sheet(xlsx_path, s) for s in sheets]
    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns=COLUMN_RENAME_MAP)
    required = set(COLUMN_RENAME_MAP.values())
    missing = required - set(df.columns)
    assert not missing, f"Missing canonical columns after rename: {missing}"
    df["line_no"] = np.arange(len(df), dtype=np.int64)
    return df


def optimise_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Downcast dtypes for memory. Logs memory usage before/after."""
    before = df.memory_usage(deep=True).sum()
    df = df.copy()

    qty_min, qty_max = df["quantity"].min(), df["quantity"].max()
    assert -2_147_483_648 <= qty_min and qty_max <= 2_147_483_647, "quantity overflow risk for int32"
    df["quantity"] = df["quantity"].astype("int32")
    df["price"] = df["price"].astype("float32")

    for col in ["country", "stock_code", "source_sheet"]:
        df[col] = df[col].astype("string")  # pyarrow 'string' dtype, not 'category'
    for col in ["invoice", "description"]:
        df[col] = df[col].astype("string")
    df["customer_id"] = df["customer_id"].astype("Float64")

    after = df.memory_usage(deep=True).sum()
    logger.info("Memory usage: %.1f MB -> %.1f MB", before / 1e6, after / 1e6)
    return df


def profile_raw(df: pd.DataFrame) -> dict:
    """Return a JSON-serialisable profile of the raw combined frame."""
    n = len(df)
    per_col = {}
    for col in df.columns:
        s = df[col]
        entry = {
            "dtype": str(s.dtype),
            "n_null": int(s.isnull().sum()),
            "pct_null": round(100 * s.isnull().mean(), 4),
            "n_unique": int(s.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(s):
            entry["min"] = float(s.min(skipna=True)) if s.notna().any() else None
            entry["max"] = float(s.max(skipna=True)) if s.notna().any() else None
        if pd.api.types.is_datetime64_any_dtype(s):
            entry["min"] = str(s.min())
            entry["max"] = str(s.max())
        per_col[col] = entry

    top_countries = df["country"].value_counts().head(10).to_dict()
    is_cancel = df["invoice"].astype(str).str.startswith("C")
    hour_hist = df["invoice_date"].dt.hour.value_counts().reindex(range(24), fill_value=0).tolist()

    return {
        "n_rows": n,
        "n_cols": df.shape[1],
        "columns": per_col,
        "top_10_countries": {str(k): int(v) for k, v in top_countries.items()},
        "n_invoices": int(df["invoice"].nunique()),
        "n_customers": int(df["customer_id"].nunique()),
        "n_stock_codes": int(df["stock_code"].nunique()),
        "pct_rows_with_C_prefix_invoice": round(100 * is_cancel.mean(), 4),
        "pct_rows_negative_quantity": round(100 * (df["quantity"] < 0).mean(), 4),
        "pct_rows_nonpositive_price": round(100 * (df["price"] <= 0).mean(), 4),
        "date_min": str(df["invoice_date"].min()),
        "date_max": str(df["invoice_date"].max()),
        "hour_histogram": hour_hist,
    }


def build_sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Stratified sample by (source_sheet, country-top10-vs-OTHER). Deterministic."""
    top10 = set(df["country"].value_counts().head(10).index)
    strata = df["source_sheet"].astype(str) + "|" + np.where(
        df["country"].isin(top10), df["country"].astype(str), "OTHER"
    )
    frac = n / len(df)
    sampled = (
        df.groupby(strata, observed=True, group_keys=False)
        .apply(lambda g: g.sample(frac=frac, random_state=seed))
    )
    if len(sampled) > n:
        sampled = sampled.sample(n=n, random_state=seed)
    elif len(sampled) < n:
        remainder = df.drop(sampled.index).sample(n=n - len(sampled), random_state=seed)
        sampled = pd.concat([sampled, remainder])
    return sampled.reset_index(drop=True)


def run(force: bool = False, sample: bool = False) -> None:
    """Stage 1 entry point."""
    logger = setup_logging("ingest")
    interim_dir = cfg.paths.interim_dir
    combined_path = interim_dir / "raw_combined.parquet"
    sample_path = interim_dir / "sample_50k.parquet"

    with timed(logger, "stage1_ingest"):
        xlsx_path = download_raw(force=force)

        if combined_path.exists() and not force:
            logger.info("raw_combined.parquet exists, loading from cache.")
            df = pd.read_parquet(combined_path)
        else:
            df = combine_sheets(xlsx_path, cfg.ingest.sheets)
            df = optimise_dtypes(df)
            df["invoice_date"] = pd.to_datetime(df["invoice_date"])
            df["amount"] = (df["quantity"].astype("float64") * df["price"].astype("float64"))
            interim_dir.mkdir(parents=True, exist_ok=True)
            df.to_parquet(combined_path, index=False)
            logger.info("Wrote %s (%d rows)", combined_path, len(df))

        profile = profile_raw(df)
        write_json(cfg.paths.metrics_dir / "stage1_profile.json", profile)

        samp = build_sample(df, cfg.ingest.sample_size, cfg.project.seed)
        samp.to_parquet(sample_path, index=False)
        logger.info("Wrote %s (%d rows)", sample_path, len(samp))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    run(force=args.force, sample=args.sample)
