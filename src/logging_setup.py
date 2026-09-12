"""Logging configuration shared by every pipeline stage."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path

from src.config import REPO_ROOT

_CONFIGURED_STAGES: set[str] = set()

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(stage: str, level: int = logging.INFO) -> logging.Logger:
    """Configure root logging to BOTH stdout and logs/pipeline_<stage>_<ts>.log.

    Idempotent: calling twice for the same stage does not duplicate handlers.
    Returns a logger named f'audit.{stage}'.
    """
    logger_name = f"audit.{stage}"
    logger = logging.getLogger(logger_name)
    if stage in _CONFIGURED_STAGES:
        return logger

    logs_dir = REPO_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"pipeline_{stage}_{ts}.log"

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_FORMAT)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    _CONFIGURED_STAGES.add(stage)
    logger.info("Logging initialised -> %s", log_path)
    return logger


@contextmanager
def timed(logger: logging.Logger, label: str):
    """Log 'START <label>' / 'DONE <label> in X.Xs'."""
    logger.info("START %s", label)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t0
        logger.info("DONE %s in %.1fs", label, elapsed)
