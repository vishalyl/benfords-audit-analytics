"""Small shared I/O helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


class NpEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy scalar/array types transparently."""

    def default(self, obj: Any) -> Any:  # noqa: D102
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


def write_json(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, cls=NpEncoder, default=str)


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
