# utils/logger.py
"""
Centralised logging configuration for BioDesign Studio.

Problem solved
--------------
The original codebase used print() for all debug/error output:

    print(f"[Dashboard] Failed to read projects: {exc}")
    print(f"[export_manager] Skipping malformed feature {feat!r}: {feat_exc}")

This meant:
  - No severity levels (can't distinguish info from errors)
  - Output goes only to the terminal -- users never see it
  - No timestamps or module names in output
  - Cannot be redirected to a log file in production

Solution
--------
This module sets up the root logger once at import time.
Every other module should do:

    import logging
    logger = logging.getLogger(__name__)

    # Then replace print() with:
    logger.debug("parsing sequence: %s", seq_id)
    logger.info("Part saved: %s", name)
    logger.warning("GC content low: %.1f%%", gc)
    logger.error("DB write failed: %s", exc, exc_info=True)

Usage (call once at app startup in app.py)
------------------------------------------
    from utils.logger import setup_logging
    setup_logging(level="INFO", log_file="logs/biodesign.log")
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    max_bytes: int = 5 * 1024 * 1024,   # 5 MB
    backup_count: int = 3,
) -> None:
    """
    Configure the root logger for BioDesign Studio.

    Parameters
    ----------
    level       : Logging level string (DEBUG / INFO / WARNING / ERROR)
    log_file    : Optional path to a rotating log file.
                  Pass None to log to console only.
    max_bytes   : Max size before log file rotation (default 5 MB).
    backup_count: Number of rotated backup files to keep.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    fmt = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove any handlers Streamlit may have already installed
    root.handlers.clear()

    # Console handler (stderr so it doesn't pollute stdout)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(fmt)
    root.addHandler(console_handler)

    # Rotating file handler (optional)
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8',
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in ('urllib3', 'biopython', 'matplotlib', 'PIL'):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        'Logging initialised -- level=%s, file=%s', level, log_file or 'console only'
    )
