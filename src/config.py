"""Configuration loader for the audit analytics pipeline.

Loads config.yaml once, exposes it as an attribute-accessible object, and
resolves every path under `paths:` to an absolute pathlib.Path, creating the
directory if it does not yet exist.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

_PATH_KEYS = {
    "raw_dir", "interim_dir", "processed_dir", "dashboard_dir",
    "figures_dir", "metrics_dir",
}
_FILE_PATH_KEYS = {"db_path"}


class Config:
    """Attribute-access wrapper around the parsed config.yaml dict.

    Nested mappings are wrapped recursively so `cfg.injection.rate` works.
    Any key under `paths` is returned as an absolute Path with parents created.
    """

    def __init__(self, data: dict, _is_paths_block: bool = False):
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_is_paths_block", _is_paths_block)

    def __getattr__(self, name: str) -> Any:
        try:
            value = self._data[name]
        except KeyError as exc:
            raise AttributeError(f"No config key '{name}'") from exc
        if isinstance(value, dict):
            return Config(value, _is_paths_block=(name == "paths"))
        if self._is_paths_block and (name in _PATH_KEYS or name in _FILE_PATH_KEYS):
            p = (REPO_ROOT / value).resolve()
            if name in _FILE_PATH_KEYS:
                p.parent.mkdir(parents=True, exist_ok=True)
            else:
                p.mkdir(parents=True, exist_ok=True)
            return p
        return value

    def to_dict(self) -> dict:
        return self._data


_CACHE: dict[str, Config] = {}


def load_config(path: Path | None = None) -> Config:
    """Load config.yaml. Caches on first call.

    Raises:
        FileNotFoundError: with a clear message naming the expected location.
    """
    key = str(path) if path else "__default__"
    if key in _CACHE:
        return _CACHE[key]
    resolved = path if path else (REPO_ROOT / "config.yaml")
    if not resolved.exists():
        raise FileNotFoundError(
            f"config.yaml not found at expected location: {resolved}"
        )
    with open(resolved, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    cfg = Config(data)
    _CACHE[key] = cfg
    return cfg


cfg = load_config()

COLUMN_RENAME_MAP: dict[str, str] = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "Price": "price",
    "Customer ID": "customer_id",
    "Country": "country",
}
