"""Shared plotting configuration and helpers, one consistent palette, no default cycling."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from src.config import cfg

PALETTE = {
    "primary": "#1F4E79",
    "secondary": "#2E75B6",
    "tertiary": "#9DC3E6",
    "risk": "#D93025",
    "warning": "#F9AB00",
    "good": "#1E8E3E",
    "neutral": "#7F7F7F",
    "dark": "#404040",
}

FIGSIZE = (10, 6)
DPI = 150

_FIGURES_INDEX_PATH = None


def _index_path() -> Path:
    global _FIGURES_INDEX_PATH
    if _FIGURES_INDEX_PATH is None:
        _FIGURES_INDEX_PATH = cfg.paths.metrics_dir / "figures_index.json"
    return _FIGURES_INDEX_PATH


def setup_style() -> None:
    plt.rcParams.update({
        "figure.figsize": FIGSIZE,
        "figure.dpi": DPI,
        "axes.prop_cycle": matplotlib.cycler(color=[
            PALETTE["primary"], PALETTE["secondary"], PALETTE["tertiary"],
            PALETTE["warning"], PALETTE["good"], PALETTE["neutral"],
        ]),
        "axes.grid": True,
        "grid.alpha": 0.3,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 11,
    })


def pct_axis(ax, axis: str = "y") -> None:
    fmt = mticker.PercentFormatter(xmax=1.0)
    if axis == "y":
        ax.yaxis.set_major_formatter(fmt)
    else:
        ax.xaxis.set_major_formatter(fmt)


def save_fig(fig, name: str, category: str = "general") -> Path:
    """Save a figure to reports/figures/<name>.png and register it in the index."""
    figures_dir = cfg.paths.figures_dir
    figures_dir.mkdir(parents=True, exist_ok=True)
    path = figures_dir / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    idx_path = _index_path()
    idx = {}
    if idx_path.exists():
        idx = json.loads(idx_path.read_text())
    idx[name] = {"path": f"reports/figures/{name}", "category": category}
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(json.dumps(idx, indent=2))
    return path


setup_style()
